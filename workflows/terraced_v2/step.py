#!/usr/bin/env python3
"""YAML-driven runner for terraced-v2.

The pipeline definition in workflow.yaml is authoritative.  This script maps each
configured module name to deterministic Python implementation while all model calls
share one provider abstraction (self/lmstudio/ollama/openrouter).
"""
from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import shutil
import sys
import time
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import vocab
from scripts.core import citations, corpus, provenance
from scripts.core import retrieval as core_retrieval
from scripts.setup_workflow import setup_workflow
from scripts.workflow_registry import read_workflow_state, write_workflow_state
from validation.scripts.package_marking import package_marking_bundle
from validation.scripts.bundled_cases import is_validation_mode, write_demo_marking_criteria_after_report
from workflows.terraced_v2 import card_identity, diagnosis_connector, layout, model_client, model_registry, rendering, runtime

WORKFLOW_ID = "terraced-v2"
HERE = Path(__file__).resolve().parent
PROMPTS = HERE / "prompts"
SETTINGS_PATH = HERE / "settings.json"
SETTINGS_TEMPLATE_PATH = HERE / "settings.json.template"
EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_HANDOFF = 10
_EXECUTION_STARTED_AT: float | None = None


class StepFailure(RuntimeError):
    pass


class Handoff(RuntimeError):
    def __init__(self, call_id: str, prompt: Path, output: Path):
        self.call_id = call_id
        self.prompt = prompt
        self.output = output
        super().__init__(call_id)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _atomic_write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
    return path


def load_settings() -> dict:
    path = SETTINGS_PATH if SETTINGS_PATH.is_file() else SETTINGS_TEMPLATE_PATH
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StepFailure(f"invalid terraced-v2 settings {path}: {exc}") from exc
    return doc


def configured_profiles() -> tuple[str | None, str | None]:
    settings = load_settings()
    model_profile = settings.get("model_profile")
    terrace_profile = settings.get("terrace_profile")
    return (
        model_profile if isinstance(model_profile, str) and model_profile else None,
        terrace_profile if isinstance(terrace_profile, str) and terrace_profile else None,
    )


class _LoggedStream:
    def __init__(self, terminal, log_handle, *, mask_terminal: bool):
        self.terminal = terminal
        self.log_handle = log_handle
        self.mask_terminal = mask_terminal
        self.buffer = ""

    def write(self, text: str) -> int:
        self.log_handle.write(text)
        self.log_handle.flush()
        if not self.mask_terminal:
            self.terminal.write(text)
            self.terminal.flush()
            return len(text)
        self.buffer += text
        while "\n" in self.buffer:
            line, self.buffer = self.buffer.split("\n", 1)
            if not (line.startswith("[retrieve]") or line.startswith("[terraced render]") or "validation pass" in line.lower()):
                self.terminal.write(line + "\n")
                self.terminal.flush()
        return len(text)

    def flush(self) -> None:
        self.log_handle.flush()
        if self.buffer and not self.mask_terminal:
            self.terminal.write(self.buffer)
            self.buffer = ""
        self.terminal.flush()

    def __getattr__(self, name):
        return getattr(self.terminal, name)


@contextlib.contextmanager
def _cli_logging(work: Path):
    log_path = work / "workflow.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        out = _LoggedStream(sys.stdout, handle, mask_terminal=False)
        err = _LoggedStream(sys.stderr, handle, mask_terminal=True)
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            yield


def _elapsed() -> int:
    global _EXECUTION_STARTED_AT
    now = time.time()
    if _EXECUTION_STARTED_AT is None:
        _EXECUTION_STARTED_AT = now
    return max(0, int(now - _EXECUTION_STARTED_AT))


def _status(message: str) -> None:
    print(f"[ {_elapsed():04d} ] - {message}", file=sys.stderr)


def _require_work(work: Path) -> dict:
    state = read_workflow_state(work)
    if state.get("workflow_id") != WORKFLOW_ID:
        raise StepFailure(f"work directory is bound to {state.get('workflow_id')!r}, not {WORKFLOW_ID!r}")
    return state


def _run_state_path(work: Path) -> Path:
    return layout.state(work, "terraced-v2-run.json", existing=False)


def _load_run_state(work: Path) -> dict:
    path = _run_state_path(work)
    if not path.is_file():
        raise StepFailure(f"missing terraced-v2 run state: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _save_run_state(work: Path, state: dict) -> None:
    _atomic_write(_run_state_path(work), json.dumps(state, indent=2, ensure_ascii=False) + "\n")


def _profile(work: Path, selector: str | None, role: str):
    return model_registry.resolve(role, selector, work)


def _bundle_paths(work: Path, call_id: str) -> tuple[Path, Path, Path]:
    """Return a stable chronologically numbered model-operation directory."""
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in call_id)
    bundle_root = layout.model_steps(work, existing=False)
    bundle_root.mkdir(parents=True, exist_ok=True)
    matching = sorted(bundle_root.glob(f"[0-9][0-9][0-9]-{safe}"))
    legacy = bundle_root / safe
    if matching:
        root = matching[0]
    elif legacy.is_dir():
        # Resume compatibility for runs created before numbered model steps.
        root = legacy
    else:
        sequence = max(
            (
                int(match.group(1))
                for path in bundle_root.iterdir()
                if path.is_dir() and (match := re.match(r"^(\d+)-", path.name))
            ),
            default=0,
        ) + 1
        root = bundle_root / f"{sequence:03d}-{safe}"
    root.mkdir(parents=True, exist_ok=True)
    return root, root / "INPUT_prompt.md", root / "INPUT_messages.json"


def _messages_markdown(messages: list[dict[str, str]]) -> str:
    lines = []
    for index, message in enumerate(messages, 1):
        lines.extend([
            f"# Message {index} — {message['role'].upper()}",
            "",
            message["content"].rstrip(),
            "",
        ])
    return "\n".join(lines).rstrip() + "\n"


def _render_bundle(call_id: str, messages: list[dict[str, str]], output: Path, validator_error: str | None = None) -> str:
    lines = [f"# Terraced-v2 model operation — {call_id}", ""]
    for i, msg in enumerate(messages, 1):
        lines.extend([f"## Message {i} — {msg['role']}", "", msg["content"].rstrip(), ""])
    if validator_error:
        lines.extend([
            "## Deterministic validator error", "", validator_error, "",
            "Revise only what is required to pass this validator; preserve unrelated clinical content.", "",
        ])
    lines.extend(["## Output", "", f"Write only the requested artifact to: `{output}`", "Do not modify any other file.", ""])
    return "\n".join(lines)


def _artifact_format(output: Path) -> str:
    suffix = output.suffix.lower()
    if suffix == ".json":
        return "JSON"
    if suffix in {".yaml", ".yml"}:
        return "YAML"
    return "TEXT"


def _normalized_name(output: Path) -> str:
    return "OUTPUT_normalized" + (output.suffix or ".txt")


def _accepted_name(output: Path) -> str:
    return "OUTPUT_accepted" + (output.suffix or ".txt")


def _normalize_candidate(text: str, output: Path, normalizer=None) -> tuple[str, list[str]]:
    normalized, repairs = runtime.normalize_model_text(text, format_name=_artifact_format(output))
    if normalizer is not None:
        normalized, extra = normalizer(normalized)
        repairs.extend(extra)
    return normalized, repairs


def _validator_name(validator) -> str:
    return getattr(validator, "__name__", validator.__class__.__name__)


def _write_json(path: Path, document: dict) -> None:
    _atomic_write(path, json.dumps(document, indent=2, ensure_ascii=False) + "\n")


def _write_call_metadata(root: Path, work: Path, *, call_id: str, role: str, binding, output: Path, attempts: int) -> None:
    try:
        target = str(output.relative_to(work))
    except ValueError:
        target = str(output)
    sequence_match = re.match(r"^(\d+)-", root.name)
    _write_json(root / "CALL_metadata.json", {
        "schema_version": 1,
        "sequence": int(sequence_match.group(1)) if sequence_match else None,
        "operation": call_id,
        "role": role,
        "profile": binding.profile,
        "provider": binding.kind,
        "model": binding.model,
        "target_output": target,
        "max_attempts": attempts,
    })


def _write_attempt_inputs(
    root: Path,
    attempt: int,
    call_id: str,
    messages: list[dict[str, str]],
    output: Path,
    validator_error: str | None,
) -> Path:
    attempt_dir = root / f"attempt_{attempt:02d}"
    attempt_dir.mkdir(parents=True, exist_ok=False)
    messages_json = json.dumps(messages, indent=2, ensure_ascii=False) + "\n"
    readable = _messages_markdown(messages)
    prompt = _render_bundle(call_id, messages, output, validator_error)
    _atomic_write(attempt_dir / "INPUT_messages.json", messages_json)
    _atomic_write(attempt_dir / "INPUT_messages_readable.md", readable)
    _atomic_write(attempt_dir / "INPUT_prompt.md", prompt)
    # Call-root files mirror the current/latest attempt for convenience.
    _atomic_write(root / "INPUT_messages.json", messages_json)
    _atomic_write(root / "INPUT_messages_readable.md", readable)
    _atomic_write(root / "INPUT_prompt.md", prompt)
    return attempt_dir


def _record_candidate(root: Path, attempt_dir: Path, *, raw: str, normalized: str, repairs: list[str], output: Path) -> None:
    repair_doc = {"changed": raw != normalized, "repairs": repairs}
    for parent in (attempt_dir, root):
        _atomic_write(parent / "OUTPUT_raw.txt", raw)
        _atomic_write(parent / _normalized_name(output), normalized)
        _write_json(parent / "OUTPUT_repairs.json", repair_doc)


def _record_validation(root: Path, attempt_dir: Path, validator, *, passed: bool, error: str | None = None) -> None:
    payload = {"passed": passed, "validator": _validator_name(validator), "error": error}
    for parent in (attempt_dir, root):
        _write_json(parent / "OUTPUT_validation.json", payload)


def _record_accepted(root: Path, attempt_dir: Path, output: Path, text: str, message: str) -> None:
    for parent in (attempt_dir, root):
        _atomic_write(parent / _accepted_name(output), text)
    _atomic_write(root / "validated.txt", message + "\n")


def _retry_messages(messages: list[dict[str, str]], previous: str, error: str) -> list[dict[str, str]]:
    return [
        *messages,
        {"role": "assistant", "content": previous},
        {
            "role": "user",
            "content": (
                "The previous output failed deterministic validation. Fix only the reported defect(s) and return "
                "the complete artifact again. Validator: " + error
            ),
        },
    ]


def _attempt_number(path: Path) -> int:
    match = re.match(r"^attempt_(\d+)$", path.name)
    return int(match.group(1)) if match else 0


def _passed_root_matches_output(root: Path, output: Path, validator) -> str | None:
    validation_path = root / "OUTPUT_validation.json"
    accepted_path = root / _accepted_name(output)
    if not (validation_path.is_file() and accepted_path.is_file() and output.is_file()):
        return None
    try:
        validation = json.loads(validation_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if validation.get("passed") is not True:
        return None
    if accepted_path.read_text(encoding="utf-8") != output.read_text(encoding="utf-8"):
        return None
    return validator(output)


def _model_call(
    work: Path,
    *,
    call_id: str,
    role: str,
    messages: list[dict[str, str]],
    output: Path,
    validator,
    profile: str | None,
    normalizer=None,
) -> str:
    """Execute one auditable model operation with deterministic pre-validation repair."""
    binding = _profile(work, profile, role)
    root, prompt_path, _messages_path = _bundle_paths(work, call_id)
    attempts = int(load_settings().get("structural_attempts", 10))
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_call_metadata(root, work, call_id=call_id, role=role, binding=binding, output=output, attempts=attempts)

    try:
        already_valid = _passed_root_matches_output(root, output, validator)
    except (ValueError, OSError, KeyError):
        already_valid = None
    if already_valid is not None:
        return already_valid

    if binding.is_self:
        attempt_dirs = sorted(
            (path for path in root.glob("attempt_[0-9][0-9]") if path.is_dir()),
            key=_attempt_number,
        )
        pending = next((path for path in reversed(attempt_dirs) if not (path / "OUTPUT_validation.json").is_file()), None)

        if pending is None:
            attempt = (_attempt_number(attempt_dirs[-1]) if attempt_dirs else 0) + 1
            if attempt > attempts:
                last_error = "unknown validation failure"
                if attempt_dirs:
                    try:
                        last_error = json.loads((attempt_dirs[-1] / "OUTPUT_validation.json").read_text(encoding="utf-8")).get("error") or last_error
                    except (OSError, json.JSONDecodeError):
                        pass
                raise StepFailure(f"model operation {call_id} failed structural validation after {attempts} attempts: {last_error}")

            validator_error = None
            call_messages = list(messages)
            if attempt_dirs:
                last = attempt_dirs[-1]
                try:
                    validation = json.loads((last / "OUTPUT_validation.json").read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    validation = {}
                if validation.get("passed") is False:
                    validator_error = validation.get("error") or "previous attempt failed deterministic validation"
                    previous_path = last / _normalized_name(output)
                    previous = previous_path.read_text(encoding="utf-8") if previous_path.is_file() else (last / "OUTPUT_raw.txt").read_text(encoding="utf-8")
                    call_messages = _retry_messages(messages, previous, validator_error)
            pending = _write_attempt_inputs(root, attempt, call_id, call_messages, output, validator_error)

        # A pre-existing target on the first migration/resume is the pending raw response.
        if not output.is_file():
            raise Handoff(call_id, prompt_path, output)

        raw = output.read_text(encoding="utf-8")
        normalized, repairs = _normalize_candidate(raw, output, normalizer)
        _record_candidate(root, pending, raw=raw, normalized=normalized, repairs=repairs, output=output)
        _atomic_write(output, normalized)
        try:
            message = validator(output)
        except (ValueError, OSError, KeyError) as exc:
            error = str(exc)
            post = output.read_text(encoding="utf-8") if output.is_file() else normalized
            if post != normalized:
                repairs = [*repairs, "validator applied an additional deterministic repair before reporting remaining errors"]
                normalized = post
                _record_candidate(root, pending, raw=raw, normalized=normalized, repairs=repairs, output=output)
            _record_validation(root, pending, validator, passed=False, error=error)
            _status(f"  {call_id}: validation failed; correction handoff required")
            # The failed raw/normalized response is safely preserved in the attempt directory.
            output.unlink(missing_ok=True)
            if _attempt_number(pending) >= attempts:
                raise StepFailure(f"model operation {call_id} failed structural validation after {attempts} attempts: {error}")
            retry_messages = _retry_messages(messages, normalized, error)
            next_attempt = _attempt_number(pending) + 1
            _write_attempt_inputs(root, next_attempt, call_id, retry_messages, output, error)
            raise Handoff(call_id, prompt_path, output)

        accepted = output.read_text(encoding="utf-8")
        if accepted != normalized:
            repairs = [*repairs, "validator applied an additional deterministic repair"]
            normalized = accepted
            _record_candidate(root, pending, raw=raw, normalized=normalized, repairs=repairs, output=output)
        _record_validation(root, pending, validator, passed=True)
        _record_accepted(root, pending, output, accepted, message)
        return message

    last_error = ""
    previous = None
    existing_attempts = sorted(
        (path for path in root.glob("attempt_[0-9][0-9]") if path.is_dir()),
        key=_attempt_number,
    )
    start_attempt = (_attempt_number(existing_attempts[-1]) if existing_attempts else 0) + 1
    if existing_attempts:
        last = existing_attempts[-1]
        validation_path = last / "OUTPUT_validation.json"
        if validation_path.is_file():
            try:
                validation = json.loads(validation_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                validation = {}
            if validation.get("passed") is False:
                last_error = validation.get("error") or "previous attempt failed deterministic validation"
                previous_path = last / _normalized_name(output)
                if previous_path.is_file():
                    previous = previous_path.read_text(encoding="utf-8")
    previous_existing = output.read_text(encoding="utf-8") if output.is_file() else None
    for attempt in range(start_attempt, attempts + 1):
        _status(f"  {call_id}: answering" if attempt == 1 else f"  {call_id}: retry {attempt - 1}/{attempts - 1}")
        call_messages = list(messages) if previous is None else _retry_messages(messages, previous, last_error)
        attempt_dir = _write_attempt_inputs(root, attempt, call_id, call_messages, output, last_error or None)
        try:
            completion = model_client.complete_messages(binding, call_messages)
        except model_client.TruncatedCompletion as exc:
            raw = exc.content
            normalized, repairs = _normalize_candidate(raw, output, normalizer)
            _record_candidate(root, attempt_dir, raw=raw, normalized=normalized, repairs=repairs, output=output)
            last_error = str(exc)
            _record_validation(root, attempt_dir, validator, passed=False, error=last_error)
            previous = normalized
            continue
        except RuntimeError as exc:
            for parent in (attempt_dir, root):
                _atomic_write(parent / "OUTPUT_api_error.txt", str(exc) + "\n")
            raise StepFailure(str(exc)) from exc

        raw = completion.content if isinstance(completion, model_client.Completion) else completion
        normalized, repairs = _normalize_candidate(raw, output, normalizer)
        _record_candidate(root, attempt_dir, raw=raw, normalized=normalized, repairs=repairs, output=output)
        _atomic_write(output, normalized)
        try:
            message = validator(output)
        except (ValueError, OSError, KeyError) as exc:
            last_error = str(exc)
            post = output.read_text(encoding="utf-8") if output.is_file() else normalized
            if post != normalized:
                repairs = [*repairs, "validator applied an additional deterministic repair before reporting remaining errors"]
                normalized = post
                _record_candidate(root, attempt_dir, raw=raw, normalized=normalized, repairs=repairs, output=output)
            _record_validation(root, attempt_dir, validator, passed=False, error=last_error)
            previous = normalized
            if previous_existing is None:
                output.unlink(missing_ok=True)
            else:
                _atomic_write(output, previous_existing)
            continue

        accepted = output.read_text(encoding="utf-8")
        if accepted != normalized:
            repairs = [*repairs, "validator applied an additional deterministic repair"]
            normalized = accepted
            _record_candidate(root, attempt_dir, raw=raw, normalized=normalized, repairs=repairs, output=output)
        _record_validation(root, attempt_dir, validator, passed=True)
        _record_accepted(root, attempt_dir, output, accepted, message)
        return message
    raise StepFailure(f"model operation {call_id} failed structural validation after {attempts} attempts: {last_error}")

def _safe_slug(text: str) -> str:
    out = "".join(ch.lower() if ch.isalnum() else "-" for ch in text).strip("-")
    while "--" in out:
        out = out.replace("--", "-")
    return out or "case"


def _timestamped_work_dir(root: Path, label: str) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = root / f"{_safe_slug(label)}-{stamp}"
    candidate = base
    suffix = 2
    while candidate.exists():
        candidate = Path(f"{base}-{suffix}")
        suffix += 1
    return candidate


def run_setup(args: argparse.Namespace) -> int:
    configured_model, configured_terrace = configured_profiles()
    registry = model_registry.load_registry()
    model_profile = model_registry.resolve_profile(
        args.model_profile or configured_model, None, registry
    )
    for role in registry["roles"]:
        model_registry.resolve(role, model_profile, None, registry)
    questions = runtime.load_questions()
    terrace_profile = (
        args.terrace_profile
        or configured_terrace
        or questions["default_execution_profile"]
    )
    if terrace_profile not in questions["execution_profiles"]:
        raise StepFailure(f"unknown terrace profile {terrace_profile!r}")

    label = args.mode
    if args.mode == "ngs-report" and args.case_file:
        label += "-" + args.case_file.stem
    elif args.mode == "nel-demo" and args.example is not None:
        label += f"-{args.example}"
    elif args.case_id:
        label += f"-{args.case_id}"
    if args.work_dir:
        work_arg = args.work_dir
    else:
        root = HERE / "runs"
        root.mkdir(parents=True, exist_ok=True)
        work_arg = _timestamped_work_dir(root, label)

    work = setup_workflow(
        workflow=WORKFLOW_ID,
        mode=args.mode,
        work_dir=work_arg,
        project=False,
        example=args.example,
        case_id=args.case_id,
    )
    write_workflow_state(work, WORKFLOW_ID, args.mode, model_profile=model_profile)
    case_path = layout.input(work, "case.md", existing=False)
    if args.case_file:
        supplied = args.case_file.expanduser().resolve()
        if not supplied.is_file():
            raise StepFailure(f"--case-file not found: {supplied}")
        shutil.copyfile(supplied, case_path)
    if not case_path.is_file() or not case_path.read_text(encoding="utf-8").strip():
        raise StepFailure(f"authoritative case.md is missing or empty: {case_path}")
    _save_run_state(work, {
        "schema_version": 1,
        "workflow_id": WORKFLOW_ID,
        "mode": args.mode,
        "validation_case": args.case_id,
        "example": args.example,
        "model_profile": model_profile,
        "terrace_profile": terrace_profile,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    with _cli_logging(work):
        print(work)
        print(f"MODEL_PROFILE={model_profile}")
        print(f"TERRACE_PROFILE={terrace_profile}")
    return EXIT_OK


def _case_json(work: Path) -> Path:
    return layout.input(work, "case.json", existing=False)


def module_structure_case(work: Path, stage: dict, profile: str | None) -> None:
    output = _case_json(work)
    if output.is_file():
        runtime.validate_case_json(output)
        return
    messages = [
        {"role": "system", "content": model_client.SYSTEM_PROMPT},
        {"role": "user", "content": (
            _read(PROMPTS / "structure_case.md")
            + "\n\n# Authoritative case.md\n" + _read(layout.input(work, "case.md"))
            + "\n\n# Allowed provisional CMC values\n" + _read(layout.input(work, "case-major-categories.json"))
            + "\n\n# NGS assay scope\n" + _read(layout.input(work, "ngs-panel-scope.md"))
        )},
    ]
    _model_call(work, call_id="structure-case", role="structure", messages=messages, output=output, validator=runtime.validate_case_json, profile=profile)


def _load_corpus() -> tuple[list[dict], list[dict], str, dict]:
    corpus_doc, _index, digest = corpus.load_corpus(corpus.DEFAULT_CORPUS, corpus.DEFAULT_INDEX)
    all_cards = corpus.flatten(corpus_doc)
    try:
        eligible = corpus.blacklist_cards(all_cards, corpus.DEFAULT_BLACKLIST)
    except ValueError as exc:
        # A paper-specific blacklist rule for a publication absent from the packaged
        # corpus is semantically inert.  Ignore only such orphaned paper rules in
        # memory; preserve all global and present-paper rules and fail on every
        # other blacklist defect.
        if "blacklist names unknown publication_key" not in str(exc):
            raise
        raw = json.loads(Path(corpus.DEFAULT_BLACKLIST).read_text(encoding="utf-8"))
        present = {card.get("publication_key") for card in all_cards}
        papers = raw.get("papers") or {}
        filtered = dict(raw)
        filtered["papers"] = {key: value for key, value in papers.items() if key in present}
        with tempfile.NamedTemporaryFile("w", suffix=".json", encoding="utf-8", delete=False) as handle:
            json.dump(filtered, handle)
            temporary = Path(handle.name)
        try:
            eligible = corpus.blacklist_cards(all_cards, temporary)
        finally:
            temporary.unlink(missing_ok=True)
    manifest = card_identity.build_manifest(all_cards, corpus_sha256=digest)
    return all_cards, eligible, digest, manifest


def _manifest_path(work: Path) -> Path:
    return layout.evidence(work, "card-identity-manifest.json", existing=False)


def _configure_manifest(work: Path) -> dict:
    path = _manifest_path(work)
    if not path.is_file():
        raise StepFailure("corpus identity has not been initialised")
    manifest = json.loads(path.read_text(encoding="utf-8"))
    diagnosis_connector.configure_runtime_card_tags(card_identity.runtime_tag_map(manifest))
    return manifest


def module_initialise_corpus(work: Path, stage: dict, profile: str | None) -> None:
    del stage, profile
    path = _manifest_path(work)
    if path.is_file():
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("algorithm") != card_identity.ALGORITHM or not manifest.get("tags"):
            raise StepFailure("existing card identity manifest is invalid")
        diagnosis_connector.configure_runtime_card_tags(card_identity.runtime_tag_map(manifest))
        return
    all_cards, _eligible, digest, manifest = _load_corpus()
    _atomic_write(path, json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    diagnosis_connector.configure_runtime_card_tags(card_identity.runtime_tag_map(manifest))
    _status(f"  corpus identity: {len(all_cards)} cards, sha256 tags initialised")


def _render_cards(cards: list[dict], manifest: dict) -> str:
    tag_by_id = card_identity.tag_by_id(manifest)
    if not cards:
        return "No eligible evidence cards were retrieved for this terrace."
    blocks = []
    for card in cards:
        tag = tag_by_id[card["card_id"]]
        blocks.append("\n".join([
            f"### [card:{tag}] {card.get('card_id')}",
            f"category: {card.get('category')}",
            f"genes: {', '.join(card.get('genes') or []) or 'none'}",
            f"diseases: {', '.join(card.get('diseases') or []) or 'none'}",
            f"evidence_tier: {card.get('evidence_tier') or 'unspecified'}",
            f"interpretation: {card.get('interpretation') or ''}",
            f"source: {card.get('paper_nickname') or ''} ({card.get('publication_year') or ''})",
        ]))
    return "\n\n".join(blocks)


def _draw_diagnosis_cards(eligible: list[dict], genes: list[str], cmcs: list[str]) -> list[dict]:
    wanted = set(genes)
    hits = []
    for source in eligible:
        matched_genes = core_retrieval.match_genes(source, wanted)
        matched_cmcs = core_retrieval._matches_case_major_category(source, cmcs)
        category = source.get("category")
        if category == "diagnosis":
            if not matched_genes and not matched_cmcs:
                continue
        elif category == "germline":
            if not matched_genes:
                continue
        else:
            continue
        card = dict(source)
        card["matched_genes"] = matched_genes
        card["matched_case_major_categories"] = matched_cmcs
        hits.append(card)
    return sorted(hits, key=lambda row: row.get("card_id") or "")


def _questions_message(domain: str, group_ids: list[str]) -> str:
    rows = runtime.questions_for_group(domain, group_ids)
    parts = [f"# Current {domain} terrace group", ""]
    for row in rows:
        parts.extend([f"## {row['id']}", row["question"], ""])
        parts.extend(f"- {line}" for line in row.get("guidance") or [])
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _final_diagnosis_prompt(question: dict) -> str:
    guidance = "\n".join(f"- {line}" for line in question.get("guidance") or [])
    schema = {
        "provisional_cmcs": [],
        "diagnoses": [],
        "supporting_facts": [{"fact": "...", "reason": "...", "source_fact_ids": ["PRE-FINAL-F1"]}],
        "uncertainties": [{"uncertainty": "...", "reason": "...", "source_ids": ["PRE-FINAL-U1"]}],
    }
    return (
        f"# {question['id']} card-free diagnostic synthesis\n\n{question['question']}\n\n"
        "This is a representation pass over an already reviewed diagnostic state, not new diagnostic reasoning.\n\n"
        "## Requirements\n" + guidance + "\n\nReturn YAML only with exactly this shape:\n\n```yaml\n"
        + yaml.safe_dump(schema, sort_keys=False, allow_unicode=True).rstrip() + "\n```\n"
    )


def _terrace_state_path(work: Path, domain: str, index: int, group_ids: list[str]) -> Path:
    """Accepted terrace state path, with resume support for pre-audit-layout runs."""
    label = group_ids[0] if len(group_ids) == 1 else f"{group_ids[0]}-{group_ids[-1]}"
    preferred = work / domain / "terraces" / f"{index:02d}-{label}.yaml"
    legacy = work / domain / f"call_{index:02d}_{label}" / "OUTPUT_state.yaml"
    if legacy.is_file() and not preferred.exists():
        return legacy
    return preferred


def _render_evidence_bundle(work: Path, domain: str, cards: list[dict], *, cmcs: list[str], diagnoses: list[str], digest: str, manifest: dict) -> tuple[Path, Path, list[dict]]:
    bundle = {
        "workflow_profile": WORKFLOW_ID,
        "terraced_domain": domain,
        "genes": runtime.read_json(_case_json(work)).get("genes") or [],
        "provisional_cmcs": cmcs,
        "accepted_schema_diseases": diagnoses,
        "diagnostic_context": [],
        "retrieved": cards,
        "runtime_card_tags": card_identity.runtime_tag_map(manifest),
        "provenance": {
            "corpus_version": None,
            "corpus_sha256": digest,
            "retrieved_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    bundle_path = layout.evidence(work, f"{domain}-bundle.json", existing=False)
    evidence_path = layout.evidence(work, f"evidence-{domain}.md", existing=False)
    tag_path = layout.evidence(work, f"card-tags-{domain}.json", existing=False)
    _atomic_write(bundle_path, json.dumps(bundle, indent=2, ensure_ascii=False) + "\n")
    result = rendering.render_to_files(bundle_path, output=evidence_path, card_tag_output=tag_path, retrieved_only=True)
    rendered_ids = {row["card_id"] for row in result.get("rendered_cards") or []}
    return evidence_path, tag_path, [card for card in cards if card.get("card_id") in rendered_ids]


def module_diagnosis_terraces(work: Path, stage: dict, profile: str | None) -> None:
    manifest = _configure_manifest(work)
    case = runtime.read_json(_case_json(work))
    _all, eligible, digest, _ = _load_corpus()
    groups = runtime.execution_groups("diagnosis", _load_run_state(work)["terrace_profile"])
    active_cmcs = list(case["provisional_cmcs"])
    fixed_genes = list(case["genes"])
    transcript: list[dict[str, str]] = []
    previous = None
    seen_cards: dict[str, dict] = {}
    audit = []
    final_doc = None
    qcfg = runtime.load_questions()
    by_id = {row["id"]: row for row in qcfg["domains"]["diagnosis"]["questions"]}

    for index, group_ids in enumerate(groups, 1):
        is_final = group_ids == ["DX-final"]
        questions_text = _questions_message("diagnosis", group_ids)
        output = _terrace_state_path(work, "diagnosis", index, group_ids)
        if is_final:
            if previous is None:
                raise StepFailure("diagnosis final synthesis requires a validated pre-final state")
            reviewed = runtime.reviewed_with_ids(previous)
            context = (
                "# Structured immutable case\n```json\n" + json.dumps(case, indent=2, ensure_ascii=False) + "\n```\n\n"
                "# Protected pre-final diagnostic state\n```yaml\n" + yaml.safe_dump(reviewed, sort_keys=False, allow_unicode=True, width=110) + "```\n"
            )
            prompt = _final_diagnosis_prompt(by_id["DX-final"])
            messages = [{"role": "system", "content": model_client.SYSTEM_PROMPT}, {"role": "user", "content": prompt + "\n\n" + context + "\n" + questions_text}]
            _model_call(
                work, call_id=f"diagnosis-{index:02d}-final", role="answer", messages=messages, output=output,
                validator=lambda p, r=reviewed, c=by_id["DX-final"]: runtime.validate_diagnosis_state(p, final=True, final_config=c, reviewed=r), profile=profile,
            )
            final_doc = runtime.parse_yaml_mapping(output)
            continue

        cards = _draw_diagnosis_cards(eligible, fixed_genes, active_cmcs)
        for card in cards:
            seen_cards.setdefault(card["card_id"], card)
        audit.append({
            "call_index": index,
            "question_ids": group_ids,
            "fixed_genes": fixed_genes,
            "provisional_cmcs": active_cmcs,
            "evidence_category": "diagnosis",
            "cards": [{"card_id": c["card_id"], "card_tag": card_identity.tag_by_id(manifest)[c["card_id"]]} for c in cards],
        })
        base_context = (
            "# Structured immutable case\n```json\n" + json.dumps(case, indent=2, ensure_ascii=False) + "\n```\n\n"
            "# NGS assay scope\n" + _read(layout.input(work, "ngs-panel-scope.md")) + "\n\n"
            "# Allowed provisional CMC values\n" + _read(layout.input(work, "case-major-categories.json")) + "\n\n"
            "# Allowed WHO5 schema_disease routing values\n" + _read(layout.input(work, "allowed-schema-diseases.json")) + "\n\n"
            "# Diagnosis/germline evidence cards\n" + _render_cards(cards, manifest)
        )
        messages = [
            {"role": "system", "content": model_client.SYSTEM_PROMPT},
            {"role": "user", "content": _read(PROMPTS / "diagnosis_terrace.md") + "\n\n" + base_context},
            *transcript,
            {"role": "user", "content": questions_text},
        ]
        _status(f"  diagnosis terrace {index}/{len(groups)-1}: draw {len(cards)} cards for CMC {' | '.join(active_cmcs)}")
        _model_call(work, call_id=f"diagnosis-{index:02d}-{'-'.join(group_ids)}", role="answer", messages=messages, output=output, validator=lambda p: runtime.validate_diagnosis_state(p), profile=profile)
        state = runtime.parse_yaml_mapping(output)
        rendered = yaml.safe_dump(state, sort_keys=False, allow_unicode=True, width=110)
        transcript.extend([{"role": "user", "content": questions_text}, {"role": "assistant", "content": rendered}])
        previous = state
        active_cmcs = list(state["provisional_cmcs"])

    if final_doc is None:
        raise StepFailure("diagnosis terraces produced no final state")
    final_path = work / "diagnosis" / "FINAL_OUTPUT.yaml"
    _atomic_write(final_path, yaml.safe_dump(final_doc, sort_keys=False, allow_unicode=True, width=110))
    cards = [seen_cards[k] for k in sorted(seen_cards)]
    _atomic_write(layout.evidence(work, "diagnosis-card-draws.json", existing=False), json.dumps(audit, indent=2, ensure_ascii=False) + "\n")
    _atomic_write(layout.evidence(work, "diagnosis-evidence.json", existing=False), json.dumps(cards, indent=2, ensure_ascii=False) + "\n")
    evidence, tags, renderable = _render_evidence_bundle(
        work, "diagnosis", cards, cmcs=list(final_doc.get("provisional_cmcs") or []),
        diagnoses=[row.get("schema_disease") for row in final_doc.get("diagnoses") or [] if row.get("schema_disease")],
        digest=digest, manifest=manifest,
    )
    _atomic_write(layout.evidence(work, "diagnosis-renderable-card-ids.json", existing=False), json.dumps([c["card_id"] for c in renderable], indent=2) + "\n")


def _diagnosis_report_synthesis_validator(path: Path) -> str:
    raw = _read(path)
    normalized, _repairs = diagnosis_connector.normalize_prose(raw)
    if normalized != raw:
        _atomic_write(path, normalized)
    diagnosis_connector.prose_to_facts(normalized)
    return "diagnosis report synthesis validated"


def module_diagnosis_report(work: Path, stage: dict, profile: str | None) -> None:
    manifest = _configure_manifest(work)
    final_doc = runtime.parse_yaml_mapping(work / "diagnosis" / "FINAL_OUTPUT.yaml")
    case = runtime.read_json(_case_json(work))
    sources = diagnosis_connector.diagnostic_sources(final_doc)
    source_input = {"structured_case": case, "reviewed_diagnostic_sources": sources}
    report_dir = work / "diagnosis" / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    prose = report_dir / "01-synthesis.md"
    messages = [{"role": "system", "content": model_client.SYSTEM_PROMPT}, {"role": "user", "content": _read(PROMPTS / "diagnosis_report_synthesis.md") + "\n\n# Synthesis input\n```yaml\n" + yaml.safe_dump(source_input, sort_keys=False, allow_unicode=True, width=110) + "```\n"}]
    _model_call(
        work, call_id="diagnosis-report-synthesis", role="summarisation", messages=messages, output=prose,
        validator=_diagnosis_report_synthesis_validator, profile=profile, normalizer=diagnosis_connector.normalize_prose,
    )
    immutable = diagnosis_connector.prose_to_facts(_read(prose))
    case_ids, diagnostic_ids = diagnosis_connector.source_id_sets(case, sources)

    grounded = work / "diagnosis" / "FINAL_FACTS.yaml"
    grounding_input = {"immutable_report": immutable, "initial_case": {"structured_case": case}, "reviewed_diagnostic_sources": sources}
    messages = [{"role": "system", "content": model_client.SYSTEM_PROMPT}, {"role": "user", "content": _read(PROMPTS / "diagnosis_report_reasons.md") + "\n\n# Grounding input\n```yaml\n" + yaml.safe_dump(grounding_input, sort_keys=False, allow_unicode=True, width=110) + "```\n"}]
    def validate_grounded(path: Path) -> str:
        doc = runtime.parse_yaml_mapping(path)
        diagnosis_connector.validate_grounded(doc, immutable, case_source_ids=case_ids, diagnostic_source_ids=diagnostic_ids)
        return "diagnosis report grounding validated"
    _model_call(work, call_id="diagnosis-report-grounding", role="summarisation", messages=messages, output=grounded, validator=validate_grounded, profile=profile)
    grounded_doc = runtime.parse_yaml_mapping(grounded)

    all_cards = json.loads(_read(layout.evidence(work, "diagnosis-evidence.json")))
    renderable_ids = set(json.loads(_read(layout.evidence(work, "diagnosis-renderable-card-ids.json"))))
    cards = [c for c in all_cards if c.get("card_id") in renderable_ids]
    tagged_cards, permitted = diagnosis_connector.runtime_cards(cards)
    aligned = work / "diagnosis" / "FINAL_ALIGNED.yaml"
    alignment_input = {"grounded_report": grounded_doc, "permitted_evidence_cards": tagged_cards}
    messages = [{"role": "system", "content": model_client.SYSTEM_PROMPT}, {"role": "user", "content": _read(PROMPTS / "diagnosis_report_alignment.md") + "\n\n# Alignment input\n```yaml\n" + yaml.safe_dump(alignment_input, sort_keys=False, allow_unicode=True, width=110) + "```\n"}]
    def validate_aligned(path: Path) -> str:
        doc = runtime.parse_yaml_mapping(path)
        diagnosis_connector.validate_aligned(doc, grounded_doc, permitted_card_tags=permitted)
        return "diagnosis report alignment validated"
    _model_call(work, call_id="diagnosis-report-alignment", role="evidence_alignment", messages=messages, output=aligned, validator=validate_aligned, profile=profile)
    _atomic_write(work / "diagnosis" / "FINAL_REPORT.md", diagnosis_connector.render_report(runtime.parse_yaml_mapping(aligned)))


def _accepted_schema_diseases(final_doc: dict) -> list[str]:
    context = runtime.diagnosis_context(final_doc)
    values = [
        row["schema_disease"]
        for row in context["who5_diagnosis"]
        if row.get("schema_disease") in vocab.CASE_DISEASE_SET
    ]
    if not values:
        # Do not promote an indeterminate WHO5 label into downstream context.
        # The explicitly propagated CMC remains the conservative broad routing
        # state when no WHO5 diagnosis is established.
        values = [cmc for cmc in context["cmc"] if cmc in vocab.CASE_DISEASE_SET]
    if not values:
        raise StepFailure("diagnosis state contains neither an established WHO5 diagnosis nor a routable CMC")
    return list(dict.fromkeys(values))


def _disease_matches(card: dict, diseases: list[str], category: str) -> list[str]:
    card_diseases = set(card.get("diseases") or [])
    matches = []
    for disease in diseases:
        allowed = {disease, *vocab.retrieval_related_diseases(disease, category)}
        if card_diseases & allowed:
            matches.append(disease)
    return matches


def _retrieve_downstream(work: Path, domain: str, category: str) -> tuple[list[dict], str, dict]:
    case = runtime.read_json(_case_json(work))
    genes = set(case.get("genes") or [])
    final_doc = runtime.parse_yaml_mapping(work / "diagnosis" / "FINAL_OUTPUT.yaml")
    diseases = _accepted_schema_diseases(final_doc)
    _all, cards, digest, manifest = _load_corpus()
    hits = []
    for source in cards:
        if source.get("category") != category:
            continue
        matched_genes = core_retrieval.match_genes(source, genes)
        if category == "germline":
            if not matched_genes:
                continue
            matched_schema = []
        else:
            matched_schema = _disease_matches(source, diseases, category)
            if not matched_schema:
                continue
            if category == "treatment" and source.get("genes") and not matched_genes:
                continue
        row = dict(source)
        row["matched_genes"] = matched_genes
        if matched_schema:
            row["matched_schema_diseases"] = matched_schema
        hits.append(row)
    hits.sort(key=lambda r: r.get("card_id") or "")
    return hits, digest, manifest


def _upstream_context(work: Path, stage: dict) -> dict:
    final_dx = runtime.parse_yaml_mapping(work / "diagnosis" / "FINAL_OUTPUT.yaml")
    dx = runtime.diagnosis_context(final_dx)
    context: dict[str, object] = {}
    requested = stage.get("context") or {}
    if "diagnosis" in requested:
        allowed = set(requested["diagnosis"])
        context["diagnosis"] = {key: value for key, value in dx.items() if key in allowed}
    for domain in ("germline", "prognosis", "biomarker", "treatment"):
        if domain not in requested:
            continue
        requested_fields = set(requested[domain])
        state = runtime.parse_yaml_mapping(work / domain / "FINAL_STATE.yaml")
        # Only facts are currently permitted cross-domain. Uncertainties and upstream issues are deliberately shed.
        context[domain] = {"facts": state.get("facts") or []} if "facts" in requested_fields else {}
    return context


def _domain_heading(domain: str) -> str:
    return {
        "germline": "**Germline**",
        "prognosis": "**Prognosis**",
        "biomarker": "**Biomarker / MRD**",
        "treatment": "**Treatment Implications**",
    }[domain]


def _render_domain_report(domain: str, aligned: dict) -> str:
    lines = [_domain_heading(domain)]
    for field, text_key in (("facts", "fact"), ("uncertainties", "uncertainty")):
        for row in aligned.get(field) or []:
            suffix = f" {row['citation']}" if row.get("citation") else ""
            lines.append(row[text_key] + suffix)
    return "\n".join(lines) + "\n" if len(lines) > 1 else ""


def module_downstream_terraces(work: Path, stage: dict, profile: str | None) -> None:
    _configure_manifest(work)
    domain = stage["domain"]
    category = stage["evidence_category"]
    case = runtime.read_json(_case_json(work))
    dx_doc = runtime.parse_yaml_mapping(work / "diagnosis" / "FINAL_OUTPUT.yaml")
    diseases = _accepted_schema_diseases(dx_doc)
    cards, digest, manifest = _retrieve_downstream(work, domain, category)
    evidence_path, tag_path, renderable = _render_evidence_bundle(work, domain, cards, cmcs=dx_doc.get("provisional_cmcs") or [], diagnoses=diseases, digest=digest, manifest=manifest)
    upstream = _upstream_context(work, stage)
    groups = runtime.execution_groups(domain, _load_run_state(work)["terrace_profile"])
    transcript: list[dict[str, str]] = []
    previous = None

    base = (
        f"# Domain\n{domain}\n\n# Immutable structured case\n```json\n" + json.dumps(case, indent=2, ensure_ascii=False) + "\n```\n\n"
        "# Settled upstream context\n```yaml\n" + yaml.safe_dump(upstream, sort_keys=False, allow_unicode=True, width=110) + "```\n\n"
        "# NGS assay scope\n" + _read(layout.input(work, "ngs-panel-scope.md")) + "\n\n"
        f"# {domain} evidence\n" + _read(evidence_path)
    )
    for index, group_ids in enumerate(groups, 1):
        questions = _questions_message(domain, group_ids)
        output = _terrace_state_path(work, domain, index, group_ids)
        messages = [
            {"role": "system", "content": model_client.SYSTEM_PROMPT},
            {"role": "user", "content": _read(PROMPTS / "downstream_terrace.md") + "\n\n" + base},
            *transcript,
            {"role": "user", "content": questions},
        ]
        _model_call(work, call_id=f"{domain}-{index:02d}-{'-'.join(group_ids)}", role="answer", messages=messages, output=output, validator=runtime.validate_domain_state, profile=profile)
        state = runtime.parse_yaml_mapping(output)
        rendered = yaml.safe_dump(state, sort_keys=False, allow_unicode=True, width=110)
        transcript.extend([{"role": "user", "content": questions}, {"role": "assistant", "content": rendered}])
        previous = state
    if previous is None:
        raise StepFailure(f"{domain} terraces produced no state")
    final_state = work / domain / "FINAL_STATE.yaml"
    _atomic_write(final_state, yaml.safe_dump(previous, sort_keys=False, allow_unicode=True, width=110))

    tag_doc = json.loads(_read(tag_path))
    permitted_tags = {row["card_tag"] for row in tag_doc.get("tags") or []}
    aligned = work / domain / "FINAL_ALIGNED.yaml"
    alignment_input = {"final_domain_state": previous, "permitted_evidence": _read(evidence_path)}
    messages = [{"role": "system", "content": model_client.SYSTEM_PROMPT}, {"role": "user", "content": _read(PROMPTS / "domain_alignment.md") + "\n\n# Alignment input\n```yaml\n" + yaml.safe_dump(alignment_input, sort_keys=False, allow_unicode=True, width=110) + "```\n"}]
    _model_call(work, call_id=f"{domain}-alignment", role="evidence_alignment", messages=messages, output=aligned, validator=lambda p: runtime.validate_domain_alignment(p, final_state, permitted_tags), profile=profile)
    _atomic_write(work / domain / "FINAL_REPORT.md", _render_domain_report(domain, runtime.parse_yaml_mapping(aligned)))


def _combined_evidence(work: Path, domains: list[str]) -> tuple[Path, Path]:
    manifest = _configure_manifest(work)
    seen: dict[str, dict] = {}
    digest = None
    for domain in domains:
        path = layout.evidence(work, f"{domain}-bundle.json")
        if not path.is_file():
            continue
        bundle = json.loads(_read(path))
        digest = digest or (bundle.get("provenance") or {}).get("corpus_sha256")
        for card in bundle.get("retrieved") or []:
            seen.setdefault(card["card_id"], card)
    bundle = {
        "workflow_profile": WORKFLOW_ID,
        "terraced_domain": "all",
        "genes": runtime.read_json(_case_json(work)).get("genes") or [],
        "provisional_cmcs": [],
        "accepted_schema_diseases": [],
        "diagnostic_context": [],
        "retrieved": [seen[k] for k in sorted(seen)],
        "runtime_card_tags": card_identity.runtime_tag_map(manifest),
        "provenance": {"corpus_version": None, "corpus_sha256": digest, "retrieved_at": datetime.now(timezone.utc).isoformat()},
    }
    bundle_path = layout.evidence(work, "all-bundle.json", existing=False)
    evidence_path = layout.evidence(work, "evidence-all.md", existing=False)
    tag_path = layout.evidence(work, "card-tags.json", existing=False)
    _atomic_write(bundle_path, json.dumps(bundle, indent=2, ensure_ascii=False) + "\n")
    rendering.render_to_files(bundle_path, output=evidence_path, card_tag_output=tag_path, retrieved_only=True)
    return evidence_path, tag_path


def _package_debug(work: Path) -> Path:
    output = work / "terraced-v2-debug.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(work.rglob("*")):
            if not path.is_file() or path == output or path.suffix == ".zip":
                continue
            archive.write(path, path.relative_to(work))
    return output


def module_finalise_report(work: Path, stage: dict, profile: str | None) -> None:
    del profile
    sections = []
    report_order = stage.get("report_order") or ["diagnosis", "prognosis", "treatment", "biomarker", "germline"]
    for domain in report_order:
        path = work / domain / "FINAL_REPORT.md"
        if path.is_file() and path.read_text(encoding="utf-8").strip():
            sections.append(path.read_text(encoding="utf-8").strip())
    if not sections:
        raise StepFailure("no report sections are available for finalisation")
    draft = "\n\n".join(sections) + "\n"
    _atomic_write(layout.synthesis(work, "report-cited.md", existing=False), draft)
    evidence, tags = _combined_evidence(work, ["diagnosis", "germline", "prognosis", "biomarker", "treatment"])
    rendered = citations.render(draft, _read(evidence), _read(tags), require_citation_after_full_stop=False)
    report = work / "report-final.md"
    _atomic_write(report, rendered)

    run_state = _load_run_state(work)
    mode = run_state.get("mode")
    if is_validation_mode(mode):
        case_id = run_state.get("validation_case")
        package_marking_bundle(mode, case_id, report)
    elif mode == "nel-demo":
        write_demo_marking_criteria_after_report(run_state.get("example"), report_path=report, output_path=work / "demo-expected.md")
    _package_debug(work)


MODULES = {
    "structure_case": module_structure_case,
    "initialise_corpus": module_initialise_corpus,
    "diagnosis_terraces": module_diagnosis_terraces,
    "diagnosis_report": module_diagnosis_report,
    "downstream_terraces": module_downstream_terraces,
    "finalise_report": module_finalise_report,
}


def run_pipeline(work: Path, *, profile: str | None = None, only_stage: str | None = None) -> int:
    _require_work(work)
    config = runtime.load_pipeline()
    stages = config["pipeline"]
    if only_stage and only_stage not in {row["id"] for row in stages}:
        raise StepFailure(f"unknown stage {only_stage!r}")
    selected = [row for row in stages if not only_stage or row["id"] == only_stage]
    for index, stage in enumerate(stages, 1):
        if stage not in selected:
            continue
        module = MODULES.get(stage["module"])
        if module is None:
            raise StepFailure(f"workflow.yaml names unsupported module {stage['module']!r}")
        _status(f"Stage {index} of {len(stages)} — {stage.get('description') or stage['id']}")
        module(work, stage, profile)
        _status(f"Stage {index} of {len(stages)} — complete")
    return EXIT_OK


def run_provider(model_profile: str | None, terrace_profile: str | None) -> int:
    if (model_profile is None) != (terrace_profile is None):
        raise StepFailure(
            "provider requires both profiles: provider <model-profile> <terrace-profile>"
        )

    configured_model, configured_terrace = configured_profiles()
    registry = model_registry.load_registry()
    questions = runtime.load_questions()
    if model_profile is not None:
        model_profile = model_registry.resolve_profile(model_profile, None, registry)
        for role in registry["roles"]:
            model_registry.resolve(role, model_profile, None, registry)
        if terrace_profile not in questions["execution_profiles"]:
            raise StepFailure(
                f"unknown terrace profile {terrace_profile!r}; choose one of: "
                + ", ".join(questions["execution_profiles"])
            )
        settings = load_settings()
        settings["model_profile"] = model_profile
        settings["terrace_profile"] = terrace_profile
        _atomic_write(SETTINGS_PATH, json.dumps(settings, indent=2, ensure_ascii=False) + "\n")
        configured_model, configured_terrace = model_profile, terrace_profile

    effective_model = model_registry.resolve_profile(configured_model, None, registry)
    effective_terrace = configured_terrace or questions["default_execution_profile"]
    print(f"MODEL_PROFILE={effective_model}")
    print(f"TERRACE_PROFILE={effective_terrace}")
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    setup = sub.add_parser("setup")
    setup.add_argument("--mode", required=True, choices=["ngs-report", "nel-demo", "nel-validate", "nel-validate-function", "nel-validate-brief"])
    setup.add_argument("--case-file", type=Path)
    setup.add_argument("--example", type=int)
    setup.add_argument("--case-id")
    setup.add_argument("--work-dir", type=Path)
    setup.add_argument("--model-profile")
    setup.add_argument("--terrace-profile")

    run = sub.add_parser("run")
    run.add_argument("--work-dir", type=Path)
    run.add_argument("--profile")
    run.add_argument("--stage")

    provider = sub.add_parser("provider")
    provider.add_argument("model_profile", nargs="?")
    provider.add_argument("terrace_profile", nargs="?")
    return parser


def main(argv: list[str] | None = None) -> int:
    global _EXECUTION_STARTED_AT
    _EXECUTION_STARTED_AT = time.time()
    args = build_parser().parse_args(argv)
    try:
        if args.command == "setup":
            if args.mode == "ngs-report" and args.case_file is None:
                raise StepFailure("ngs-report requires --case-file case.md")
            if args.mode == "nel-demo" and args.example is None:
                raise StepFailure("nel-demo requires --example N")
            if is_validation_mode(args.mode) and not args.case_id:
                raise StepFailure(f"{args.mode} requires --case-id ID")
            return run_setup(args)
        if args.command == "provider":
            if (args.model_profile is None) != (args.terrace_profile is None):
                raise StepFailure("provider requires both model-profile and terrace-profile, or neither")
            return run_provider(args.model_profile, args.terrace_profile)
        if args.work_dir:
            work = args.work_dir.expanduser().resolve()
        else:
            runs_root = HERE / "runs"
            if not runs_root.is_dir():
                raise StepFailure("no --work-dir given and no runs/ directory found")
            candidates = sorted(
                [p for p in runs_root.iterdir() if p.is_dir()],
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            if not candidates:
                raise StepFailure("no --work-dir given and runs/ is empty")
            work = candidates[0]
            _status(f"using most recent run directory: {work}")
        with _cli_logging(work):
            return run_pipeline(work, profile=args.profile, only_stage=args.stage)
    except Handoff as handoff:
        print(f"HANDOFF={handoff.call_id}")
        print(f"PROMPT={handoff.prompt}")
        print(f"OUTPUT={handoff.output}")
        return EXIT_HANDOFF
    except (StepFailure, ValueError, OSError, KeyError, json.JSONDecodeError, yaml.YAMLError) as exc:
        print(f"terraced-v2 failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
