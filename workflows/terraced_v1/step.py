#!/usr/bin/env python3
"""State-machine CLI for terraced-v1.

The same workflow can be executed by a frontier/session model (profile ``self``)
or directly against OpenAI-compatible LM Studio, Ollama, or OpenRouter profiles.
For ``self`` bindings the CLI writes an exact prompt bundle, returns exit 10, and
resumes when the requested output file has been completed.

Canonical workflow steps: 1a 1b 2 3 4 5 6 7
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import zipfile
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.workflow_registry import read_workflow_state, write_workflow_state  # noqa: E402
from workflows.terraced_v1 import model_client, model_registry, retrieval, runtime  # noqa: E402

WORKFLOW_ID = "terraced-v1"
WORKFLOW_DIR = Path(__file__).resolve().parent
PROMPTS = WORKFLOW_DIR / "prompts"
SHARED_PROMPTS = REPO_ROOT / "prompts" / "workflow"
SETTINGS_PATH = WORKFLOW_DIR / "settings.json"
SETTINGS_TEMPLATE_PATH = WORKFLOW_DIR / "settings.json.template"
BUNDLE_DIR = ".model-steps"
BUNDLE_ZIP = "ngs-report-model-steps.zip"
USAGE_FILE = "model-usage.json"
PROJECT_ROOT = REPO_ROOT / "temp"
PROJECT_POINTER = PROJECT_ROOT / ".terraced-v1-project"
WORK_DIR_ENV = "NEL_WORK_DIR"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_HANDOFF = 10
EXIT_NOT_REQUIRED = 20
DOMAINS = runtime.DOMAINS
DOWNSTREAM = ("prognosis", "treatment", "mrd", "germline")
STEP_DESCRIPTIONS = {
    "1a": "capture case",
    "1b": "structure case",
    "2": "retrieve diagnostic evidence",
    "3": "run terraced diagnosis",
    "4": "review and align diagnosis evidence",
    "5": "run downstream categories",
    "6": "synthesise, align citations, and render",
    "7": "package workflow outputs",
}


class StepFailure(RuntimeError):
    pass


class Handoff(RuntimeError):
    def __init__(self, call_id: str, prompt: Path, output: Path):
        self.call_id = call_id
        self.prompt = prompt
        self.output = output
        super().__init__(call_id)


def load_settings() -> dict:
    path = SETTINGS_PATH if SETTINGS_PATH.is_file() else SETTINGS_TEMPLATE_PATH
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"semantic_review_cycles": 2, "structural_attempts": 10, "token_budget": 120000}
    return doc


def configured_profiles() -> tuple[str | None, str | None]:
    settings = load_settings()
    model_profile = settings.get("model_profile")
    terrace_profile = settings.get("terrace_profile")
    return (
        model_profile if isinstance(model_profile, str) and model_profile else None,
        terrace_profile if isinstance(terrace_profile, str) and terrace_profile else None,
    )


def _atomic_write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)
    return path


def _require_work(work: Path) -> dict:
    state = read_workflow_state(work)
    if state.get("workflow_id") != WORKFLOW_ID:
        raise StepFailure(f"work directory is bound to {state.get('workflow_id')!r}, not {WORKFLOW_ID!r}")
    return state


def _write_project_pointer(work: Path) -> None:
    work = work.resolve()
    PROJECT_ROOT.mkdir(exist_ok=True)
    if not work.is_relative_to(PROJECT_ROOT.resolve()):
        raise StepFailure(f"project work directory must be under {PROJECT_ROOT.resolve()}")
    _atomic_write(PROJECT_POINTER, str(work) + "\n")


def resolve_work_dir(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit.expanduser().resolve()
    env = os.environ.get(WORK_DIR_ENV, "").strip()
    if env:
        work = Path(env).expanduser().resolve()
        _require_work(work)
        return work
    if PROJECT_POINTER.is_file():
        work = Path(PROJECT_POINTER.read_text(encoding="utf-8").strip()).resolve()
        _require_work(work)
        return work
    raise StepFailure(f"--work-dir is required unless {WORK_DIR_ENV} or setup --project selects a terraced project")


def _run_state_path(work: Path) -> Path:
    return work / "terraced-run.json"


def _load_run_state(work: Path) -> dict:
    path = _run_state_path(work)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StepFailure(f"invalid terraced run state {path}: {exc}") from exc


def _save_run_state(work: Path, state: dict) -> None:
    _atomic_write(_run_state_path(work), json.dumps(state, indent=2, ensure_ascii=False) + "\n")


def _profile(work: Path, selector: str | None, role: str):
    return model_registry.resolve(role, selector, work)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise StepFailure(f"cannot read required model input {path}: {exc}") from exc


def _bundle_paths(work: Path, call_id: str) -> tuple[Path, Path, Path]:
    bundle_root = work / BUNDLE_DIR
    bundle_root.mkdir(parents=True, exist_ok=True)
    matching = sorted(bundle_root.glob(f"[0-9][0-9][0-9]-{call_id}"))
    legacy = bundle_root / call_id
    if matching:
        root = matching[0]
    elif legacy.is_dir():
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
        root = bundle_root / f"{sequence:03d}-{call_id}"
    root.mkdir(parents=True, exist_ok=True)
    return root, root / "prompt.md", root / "messages.json"


def _record_usage(
    work: Path,
    call_id: str,
    model: str,
    attempt: int,
    usage: dict[str, int] | None,
) -> None:
    path = work / USAGE_FILE
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        document = {"schema_version": 1, "calls": []}
    document.setdefault("calls", []).append(
        {
            "operation": call_id,
            "model": model,
            "attempt": attempt,
            "usage": usage,
        }
    )
    _atomic_write(path, json.dumps(document, indent=2, ensure_ascii=False) + "\n")


def _print_usage(work: Path) -> None:
    path = work / USAGE_FILE
    if not path.is_file():
        print("Token usage: unavailable (self handoff or provider did not report usage)", file=sys.stderr)
        return
    try:
        calls = json.loads(path.read_text(encoding="utf-8")).get("calls", [])
    except (OSError, json.JSONDecodeError):
        print("Token usage: unavailable (usage ledger could not be read)", file=sys.stderr)
        return
    reported = [row["usage"] for row in calls if isinstance(row.get("usage"), dict)]
    missing = len(calls) - len(reported)
    totals = {
        key: sum(usage.get(key, 0) for usage in reported)
        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
    }
    if not reported:
        print("Token usage: unavailable (provider did not report usage)", file=sys.stderr)
        return
    suffix = f"; partial, {missing} attempt(s) unreported" if missing else ""
    print(
        "Token usage: "
        f"prompt {totals['prompt_tokens']:,}, completion {totals['completion_tokens']:,}, "
        f"total {totals['total_tokens']:,}{suffix}",
        file=sys.stderr,
    )


def _render_bundle(call_id: str, messages: list[dict[str, str]], output: Path, validator_error: str | None = None) -> str:
    lines = [f"# Terraced-v1 model operation — {call_id}", ""]
    for i, msg in enumerate(messages, start=1):
        lines.extend([f"## Message {i} — {msg['role']}", "", msg["content"].rstrip(), ""])
    if validator_error:
        lines.extend([
            "## Deterministic validator error",
            "",
            validator_error,
            "",
            "Revise the requested output to fix this error. Preserve clinical content not implicated by the error.",
            "",
        ])
    lines.extend([
        "## Output",
        "",
        f"Write only the requested artifact to: `{output}`",
        "Do not modify any other file.",
        "",
    ])
    return "\n".join(lines)


def _model_call(
    work: Path,
    *,
    call_id: str,
    role: str,
    messages: list[dict[str, str]],
    output: Path,
    validator,
    profile: str | None,
) -> str:
    """Complete one model operation, handing off to the session model when needed."""
    binding = _profile(work, profile, role)
    root, prompt_path, messages_path = _bundle_paths(work, call_id)
    attempts = int(load_settings().get("structural_attempts", 10))

    # A self handoff resumes by validating the already-authored target.
    if binding.is_self:
        validator_error = None
        if output.is_file():
            try:
                message = validator(output)
                _atomic_write(root / "validated.txt", message + "\n")
                print(f"  {call_id}: validated", file=sys.stderr)
                return message
            except (ValueError, OSError, KeyError) as exc:
                validator_error = str(exc)
                _atomic_write(root / "attempt-self.validation.txt", validator_error + "\n")
                print(f"  {call_id}: validation failed; handoff needs correction", file=sys.stderr)
        _atomic_write(messages_path, json.dumps(messages, indent=2, ensure_ascii=False) + "\n")
        _atomic_write(prompt_path, _render_bundle(call_id, messages, output, validator_error))
        raise Handoff(call_id, prompt_path, output)

    last_error = ""
    previous = None
    for attempt in range(1, attempts + 1):
        print(f"  {call_id}: model attempt {attempt} of {attempts}", file=sys.stderr)
        call_messages = list(messages)
        if previous is not None:
            call_messages.extend([
                {"role": "assistant", "content": previous},
                {
                    "role": "user",
                    "content": (
                        "The previous output failed deterministic structural validation. Fix only the reported "
                        f"defect(s) and return the complete artifact again. Validator: {last_error}"
                    ),
                },
            ])
        _atomic_write(messages_path, json.dumps(call_messages, indent=2, ensure_ascii=False) + "\n")
        _atomic_write(prompt_path, _render_bundle(call_id, call_messages, output, last_error or None))
        try:
            completion = model_client.complete_messages(binding, call_messages)
        except model_client.TruncatedCompletion as exc:
            _record_usage(work, call_id, binding.model, attempt, exc.usage)
            previous = exc.content
            last_error = str(exc)
            _atomic_write(root / f"attempt-{attempt}.validation.txt", last_error + "\n")
            print(f"  {call_id}: output truncated; retrying", file=sys.stderr)
            continue
        except RuntimeError as exc:
            raise StepFailure(str(exc)) from exc
        if isinstance(completion, model_client.Completion):
            raw = completion.content
            usage = completion.usage
        else:
            # Preserve compatibility with local integrations and test doubles that return text.
            raw = completion
            usage = None
        _record_usage(work, call_id, binding.model, attempt, usage)
        text = model_client.strip_code_fence(raw)
        _atomic_write(root / f"attempt-{attempt}.output", text)
        previous_existing = output.read_text(encoding="utf-8") if output.is_file() else None
        _atomic_write(output, text)
        try:
            message = validator(output)
        except (ValueError, OSError, KeyError) as exc:
            last_error = str(exc)
            _atomic_write(root / f"attempt-{attempt}.validation.txt", last_error + "\n")
            previous = text
            if previous_existing is None:
                output.unlink(missing_ok=True)
            else:
                _atomic_write(output, previous_existing)
            print(f"  {call_id}: validation failed; retrying", file=sys.stderr)
            continue
        _atomic_write(root / "validated.txt", message + "\n")
        print(f"  {call_id}: validated", file=sys.stderr)
        return message
    raise StepFailure(f"model operation {call_id} failed structural validation after {attempts} attempts: {last_error}")


def _conversation_path(work: Path, domain: str) -> Path:
    return work / f"conversation-{domain}.json"


def _conversation(work: Path, domain: str) -> list[dict]:
    path = _conversation_path(work, domain)
    if not path.is_file():
        return []
    doc = json.loads(path.read_text(encoding="utf-8"))
    return doc if isinstance(doc, list) else []


def _append_turn(work: Path, domain: str, call_id: str, question: str, answer: str) -> None:
    rows = _conversation(work, domain)
    if any(row.get("call_id") == call_id for row in rows):
        return
    rows.append({"call_id": call_id, "user": question, "assistant": answer})
    _atomic_write(_conversation_path(work, domain), json.dumps(rows, indent=2, ensure_ascii=False) + "\n")


def _prior_messages(work: Path, domain: str) -> list[dict[str, str]]:
    messages = []
    for row in _conversation(work, domain):
        messages.append({"role": "user", "content": row["user"]})
        messages.append({"role": "assistant", "content": row["assistant"]})
    return messages


def _upstream_context(work: Path, domain: str) -> str:
    if domain == "diagnosis":
        return "None; diagnosis is the routing category."
    parts = []
    for prior in DOMAINS:
        if prior == domain:
            break
        path = work / f"category-{prior}.yaml"
        if path.is_file():
            parts.extend([f"## Accepted {prior}", _read(path)])
    return "\n\n".join(parts) if parts else "None."


def _base_context(work: Path, domain: str) -> str:
    evidence = work / f"evidence-{domain}.md"
    sections = [
        "# Stable clinical context for this category",
        "",
        "## Case",
        _read(work / "case.md"),
        "## Structured case",
        _read(work / "case-input.json"),
        "## NGS assay scope",
        _read(work / "ngs-panel-scope.md"),
        "## Accepted upstream clinical state",
        _upstream_context(work, domain),
        f"## {domain} evidence cards",
        _read(evidence),
    ]
    if domain == "diagnosis":
        sections.extend(["## Allowed final schema_disease routing values", _read(work / "allowed-schema-diseases.json")])
    return "\n\n".join(section.rstrip() for section in sections) + "\n"


def _question_message(work: Path, domain: str, group_ids: list[str]) -> str:
    rows = runtime.questions_for_group(work, domain, group_ids)
    lines = [
        f"# Current {domain} terrace group",
        "",
        "Work through the following questions in order. Each later question must reconsider the complete current interpretation.",
        "Only the final revised category state is returned; do not expose hidden chain-of-thought.",
        "",
    ]
    for row in rows:
        lines.extend([f"## {row['id']}", row["question"], ""])
        for item in row.get("guidance") or []:
            lines.append(f"- {item}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _terrace_messages(work: Path, domain: str, group_ids: list[str]) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": model_client.SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _read(PROMPTS / "terrace_answer.md") + "\n\n" + _base_context(work, domain),
        },
        *_prior_messages(work, domain),
        {"role": "user", "content": _question_message(work, domain, group_ids)},
    ]


def _domain_answer_path(work: Path, domain: str) -> Path:
    return work / f"answer-{domain}.yaml"


def _latest_group_path(work: Path, domain: str, index: int) -> Path:
    return work / f"terrace-{domain}-{index}.yaml"


def _refresh_diagnosis_if_needed(work: Path, answer_path: Path) -> None:
    doc = yaml.safe_load(answer_path.read_text(encoding="utf-8"))
    requested = list(doc.get("provisional_cmcs") or [])
    existing_doc = json.loads((work / "evidence-diagnosis.json").read_text(encoding="utf-8"))
    existing = list(existing_doc.get("provisional_cmcs") or [])
    combined = list(dict.fromkeys(existing + requested))
    if combined != existing:
        retrieval.diagnosis(work, combined)
        runtime.render_evidence(work, "diagnosis")


def run_terraces(work: Path, domain: str, profile: str | None) -> Path:
    run_state = _load_run_state(work)
    terrace_profile = run_state["terrace_profile"]
    groups = runtime.execution_groups(work, domain, terrace_profile)
    for index, group_ids in enumerate(groups, start=1):
        output = _latest_group_path(work, domain, index)
        final = index == len(groups)
        call_id = f"terrace-{domain}-{index}"
        question = _question_message(work, domain, group_ids)
        _model_call(
            work,
            call_id=call_id,
            role="answer",
            messages=_terrace_messages(work, domain, group_ids),
            output=output,
            validator=lambda path, d=domain, f=final: runtime.validate_category_answer(path, d, final=f, aligned=False),
            profile=profile,
        )
        _append_turn(work, domain, call_id, question, _read(output))
        if domain == "diagnosis":
            _refresh_diagnosis_if_needed(work, output)
    latest = _latest_group_path(work, domain, len(groups))
    shutil.copyfile(latest, _domain_answer_path(work, domain))
    runtime.validate_category_answer(_domain_answer_path(work, domain), domain, final=True, aligned=False)
    return _domain_answer_path(work, domain)


def _semantic_messages(work: Path, domain: str, answer: Path) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": model_client.SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                _read(PROMPTS / "semantic_review.md")
                + "\n\n"
                + _base_context(work, domain)
                + f"\n\n## Completed {domain} answer\n\n"
                + _read(answer)
            ),
        },
    ]


def _repair_messages(work: Path, domain: str, issues: list[str], answer: Path) -> list[dict[str, str]]:
    return [
        *_terrace_messages(work, domain, runtime.execution_groups(work, domain, _load_run_state(work)["terrace_profile"])[-1]),
        {
            "role": "user",
            "content": (
                _read(PROMPTS / "repair_category.md")
                + "\n\n## Reviewer issues\n"
                + "\n".join(f"- {issue}" for issue in issues)
                + "\n\n## Current complete category state\n"
                + _read(answer)
            ),
        },
    ]


def semantic_review_and_repair(work: Path, domain: str, profile: str | None) -> None:
    settings = load_settings()
    max_cycles = int(settings.get("semantic_review_cycles", 2))
    answer = _domain_answer_path(work, domain)
    for cycle in range(0, max_cycles + 1):
        review = work / f"review-{domain}.json"
        call_id = f"review-{domain}-{cycle + 1}"
        _model_call(
            work,
            call_id=call_id,
            role="semantic_review",
            messages=_semantic_messages(work, domain, answer),
            output=review,
            validator=lambda path: "semantic review structurally valid" if runtime.validate_review(path) else "",
            profile=profile,
        )
        passed, issues = runtime.validate_review(review)
        if passed:
            return
        if cycle >= max_cycles:
            raise StepFailure(f"{domain} retained material semantic defects after {max_cycles} repair cycle(s): {'; '.join(issues)}")
        repair = work / f"repair-{domain}-{cycle + 1}.yaml"
        _model_call(
            work,
            call_id=f"repair-{domain}-{cycle + 1}",
            role="answer",
            messages=_repair_messages(work, domain, issues, answer),
            output=repair,
            validator=lambda path, d=domain: runtime.validate_category_answer(path, d, final=True, aligned=False),
            profile=profile,
        )
        shutil.copyfile(repair, answer)
        _append_turn(
            work,
            domain,
            f"repair-{domain}-{cycle + 1}",
            "Semantic review findings:\n" + "\n".join(f"- {x}" for x in issues),
            _read(repair),
        )
        review.unlink(missing_ok=True)
        if domain == "diagnosis":
            _refresh_diagnosis_if_needed(work, answer)


def evidence_alignment(work: Path, domain: str, profile: str | None) -> Path:
    answer = _domain_answer_path(work, domain)
    aligned = work / f"category-{domain}.yaml"
    evidence = work / f"evidence-{domain}.md"
    messages = [
        {"role": "system", "content": model_client.SYSTEM_PROMPT},
        {
            "role": "user",
            "content": (
                _read(PROMPTS / "evidence_alignment.md")
                + f"\n\n## Final {domain} answer\n\n"
                + _read(answer)
                + f"\n\n## Permitted {domain} evidence\n\n"
                + _read(evidence)
            ),
        },
    ]
    _model_call(
        work,
        call_id=f"align-{domain}",
        role="evidence_alignment",
        messages=messages,
        output=aligned,
        validator=lambda path: runtime.validate_alignment(answer, path, domain, evidence),
        profile=profile,
    )
    return aligned


def _case_capture_validator(path: Path) -> str:
    if not path.is_file() or not path.read_text(encoding="utf-8").strip():
        raise ValueError("case.md is empty")
    return "case.md captured"


def step_1a(work: Path, profile: str | None) -> int:
    mode = _require_work(work).get("mode")
    if mode in {"nel-validate", "nel-validate-function"}:
        return EXIT_NOT_REQUIRED
    source = work / "case-source.md"
    messages = [
        {"role": "system", "content": model_client.SYSTEM_PROMPT},
        {"role": "user", "content": _read(SHARED_PROMPTS / "capture_case.md") + "\n\n## Case source\n\n" + _read(source)},
    ]
    _model_call(work, call_id="1a-case-capture", role="structure", messages=messages, output=work / "case.md", validator=_case_capture_validator, profile=profile)
    return EXIT_OK


def step_1b(work: Path, profile: str | None) -> int:
    messages = [
        {"role": "system", "content": model_client.SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _read(PROMPTS / "structure_case.md") + "\n\n## Case\n\n" + _read(work / "case.md") + "\n\n## Allowed CMCs\n\n" + _read(work / "case-major-categories.json"),
        },
    ]
    _model_call(work, call_id="1b-structure-case", role="structure", messages=messages, output=work / "case-input.json", validator=lambda _p: runtime.validate_case_input(work), profile=profile)
    return EXIT_OK


def step_2(work: Path) -> int:
    runtime.validate_case_input(work)
    retrieval.diagnosis(work)
    runtime.render_evidence(work, "diagnosis")
    return EXIT_OK


def step_3(work: Path, profile: str | None) -> int:
    run_terraces(work, "diagnosis", profile)
    return EXIT_OK


def step_4(work: Path, profile: str | None) -> int:
    semantic_review_and_repair(work, "diagnosis", profile)
    evidence_alignment(work, "diagnosis", profile)
    return EXIT_OK


def step_5(work: Path, profile: str | None) -> int:
    for index, domain in enumerate(DOWNSTREAM, start=1):
        print(f"  Downstream category {index} of {len(DOWNSTREAM)} — {domain}", file=sys.stderr)
        category = work / f"category-{domain}.yaml"
        if category.is_file():
            runtime.validate_category_answer(category, domain, final=True, aligned=True)
            print(f"  {domain}: existing aligned category validated", file=sys.stderr)
            continue
        retrieval.downstream(work, domain)
        runtime.render_evidence(work, domain)
        run_terraces(work, domain, profile)
        semantic_review_and_repair(work, domain, profile)
        evidence_alignment(work, domain, profile)
    return EXIT_OK


def _summary_validator(path: Path) -> str:
    text = _read(path).strip()
    issues = []
    if not text:
        issues.append(
            "Report — Problem: summary is empty. Required fix: return the complete uncited report under supported domain headings."
        )
    else:
        if "[card:" in text:
            issues.append(
                "Report — Problem: uncited summary contains runtime card-tag syntax. Required fix: remove every [card:......] tag."
            )
        if "## References" in text:
            issues.append(
                "Report — Problem: uncited summary contains a References heading/bibliography. Required fix: remove the bibliography entirely."
            )
        if "(no citation required)" in text:
            issues.append(
                "Report — Problem: uncited summary contains '(no citation required)'. Required fix: remove every citation disposition marker."
            )
        _, manifest_issues = _summary_manifest_and_issues(text)
        issues.extend(manifest_issues)
    _raise_model_validation_issues("uncited report draft", issues)
    return "uncited report draft validated"


def _plain_from_cited(text: str) -> str:
    text = re.sub(r"\. (?:\[card:[0-9a-f]{6}\])+(?=\s|$)", ".", text)
    text = re.sub(r"\. \(no citation required\)(?=\s|$)", ".", text)
    return text


SUMMARY_HEADINGS = {
    "Diagnosis": "diagnosis",
    "Prognosis": "prognosis",
    "Treatment Implications": "treatment",
    "MRD": "mrd",
    "Germline": "germline",
}
SUMMARY_HEADING_RE = re.compile(r"^\*\*(?P<title>[^*]+)\*\*[ \t]*$", re.MULTILINE)
SUMMARY_MARKDOWN_HEADING_RE = re.compile(r"^#{1,6}[ \t]+(?P<title>.+?)[ \t]*$", re.MULTILINE)
SUMMARY_SENTENCE_END_RE = re.compile(r"\.(?=\s|$)")
RUNTIME_CARD_TAG_RE = re.compile(r"\[card:([0-9a-f]{6})\]")


def _raise_model_validation_issues(context: str, issues: list[str]) -> None:
    if issues:
        rendered = "\n".join(f"{index}. {issue}" for index, issue in enumerate(issues, start=1))
        raise ValueError(f"{context} failed validation with {len(issues)} issue(s):\n{rendered}")


def _summary_manifest_and_issues(draft: str) -> tuple[list[dict], list[str]]:
    """Return sentence spans plus every deterministic summary-format defect detectable in one pass."""
    allowed = ", ".join(f"**{title}**" for title in SUMMARY_HEADINGS)
    issues = []
    markers = []
    for match in SUMMARY_HEADING_RE.finditer(draft):
        title = match.group("title")
        markers.append((match.start(), match.end(), "bold", title, match))
        if title not in SUMMARY_HEADINGS:
            issues.append(
                f"Heading {title!r} — Problem: unsupported standalone bold heading. Required fix: remove it or replace it with one exact allowed heading: {allowed}."
            )
    for match in SUMMARY_MARKDOWN_HEADING_RE.finditer(draft):
        title = match.group("title")
        markers.append((match.start(), match.end(), "markdown", title, match))
        issues.append(
            f"Markdown heading {match.group(0)!r} — Problem: Markdown '#' headings are not supported. Required fix: remove it or use one exact standalone bold heading: {allowed}."
        )
    markers.sort(key=lambda row: row[0])
    supported = [row for row in markers if row[2] == "bold" and row[3] in SUMMARY_HEADINGS]
    if not supported:
        issues.append(
            "Report — Problem: no supported domain heading was found, so no report sentence can be indexed. "
            f"Required fix: put every report sentence under an exact standalone heading from: {allowed}."
        )

    first_marker_start = markers[0][0] if markers else len(draft)
    if draft[:first_marker_start].strip():
        issues.append(
            "Report preamble — Problem: text appears before the first domain heading. "
            f"Required fix: remove the preamble or move each sentence under an exact allowed heading: {allowed}."
        )

    title_counts = {}
    sentences = []
    domain_counts = {domain: 0 for domain in SUMMARY_HEADINGS.values()}
    for marker_index, marker in enumerate(markers):
        start, end, kind, title, _match = marker
        section_end = markers[marker_index + 1][0] if marker_index + 1 < len(markers) else len(draft)
        body = draft[end:section_end]
        if kind != "bold" or title not in SUMMARY_HEADINGS:
            if body.strip():
                issues.append(
                    f"Unsupported heading {title!r} — Problem: text follows a heading that cannot be indexed into a clinical domain. "
                    f"Required fix: move that text under one exact allowed heading: {allowed}."
                )
            continue
        title_counts[title] = title_counts.get(title, 0) + 1
        if title_counts[title] > 1:
            issues.append(
                f"Heading **{title}** — Problem: duplicate supported heading. "
                "Required fix: merge all content for this domain under a single heading and remove the duplicate heading."
            )
        domain = SUMMARY_HEADINGS[title]
        sentence_start = end
        section_sentence_count = 0
        for ending in SUMMARY_SENTENCE_END_RE.finditer(draft, end, section_end):
            sentence_end = ending.end()
            sentence_text = draft[sentence_start:sentence_end].strip()
            if not sentence_text:
                issues.append(
                    f"**{title}** — Problem: an empty full-stop-delimited sentence was detected. Required fix: remove the stray full stop/whitespace."
                )
            else:
                domain_counts[domain] += 1
                section_sentence_count += 1
                sentences.append(
                    {
                        "sentence_id": f"{domain}-{domain_counts[domain]}",
                        "domain": domain,
                        "sentence": sentence_text,
                        "end": sentence_end,
                    }
                )
            sentence_start = sentence_end
        trailing = draft[sentence_start:section_end].strip()
        if trailing:
            issues.append(
                f"**{title}** — Problem: trailing text does not end in a full stop: {trailing!r}. "
                "Required fix: make every sentence complete and end it with a full stop."
            )
        if section_sentence_count == 0 and not body.strip():
            issues.append(
                f"**{title}** — Problem: heading has no report sentence. Required fix: remove the empty heading, or add a fact-supported full-stop-terminated sentence."
            )
    if supported and not sentences:
        issues.append(
            "Report — Problem: supported headings were present but no complete full-stop-terminated sentences were found. "
            "Required fix: include at least one complete fact-supported sentence under a supported heading."
        )
    return sentences, issues


def _summary_sentence_manifest(draft: str) -> list[dict]:
    """Index sentence spans without changing any report bytes."""
    sentences, issues = _summary_manifest_and_issues(draft)
    _raise_model_validation_issues("uncited report draft", issues)
    return sentences

def _accepted_fact_manifest(work: Path) -> list[dict]:
    facts = []
    for domain in DOMAINS:
        document = yaml.safe_load(_read(work / f"category-{domain}.yaml"))
        rows = document["facts"] if domain == "diagnosis" else document
        for index, row in enumerate(rows, start=1):
            facts.append(
                {
                    "fact_id": f"{domain}-{index}",
                    "domain": domain,
                    "fact": row["fact"],
                    "reason": row["reason"],
                    "citation": row["citation"],
                }
            )
    return facts


def _citation_alignment_input(work: Path, draft: str) -> str:
    sentences = [
        {key: row[key] for key in ("sentence_id", "domain", "sentence")}
        for row in _summary_sentence_manifest(draft)
    ]
    return yaml.safe_dump(
        {"sentences": sentences, "accepted_facts": _accepted_fact_manifest(work)},
        sort_keys=False,
        allow_unicode=True,
        width=100,
    )


def _load_sentence_fact_alignment(work: Path, path: Path) -> tuple[list[dict], dict[str, dict], dict[str, list[str]]]:
    draft = _read(work / "report-draft.md")
    sentences = _summary_sentence_manifest(draft)
    facts = {row["fact_id"]: row for row in _accepted_fact_manifest(work)}
    try:
        document = yaml.safe_load(_read(path))
    except yaml.YAMLError as exc:
        mark = getattr(exc, "problem_mark", None)
        where = f" at line {mark.line + 1}, column {mark.column + 1}" if mark is not None else ""
        problem = getattr(exc, "problem", None) or str(exc)
        raise ValueError(
            f"citation alignment failed validation with 1 issue(s):\n"
            f"1. YAML — Problem: parser error{where}: {problem}. Required fix: return one complete syntactically valid YAML object only."
        ) from exc

    issues = []
    if not isinstance(document, dict):
        _raise_model_validation_issues(
            "citation alignment",
            [
                "Top level — Problem: expected a YAML object containing exactly 'alignments'. "
                f"Received {type(document).__name__}. Required fix: return the complete alignments object."
            ],
        )
    expected_top = {"alignments"}
    missing_top = sorted(expected_top - set(document))
    unexpected_top = sorted(set(document) - expected_top)
    if missing_top:
        issues.append("Top level — Problem: missing 'alignments'. Required fix: add the alignments field.")
    if unexpected_top:
        issues.append(
            f"Top level — Problem: unexpected field(s): {', '.join(unexpected_top)}. "
            "Required fix: for a matched result return only 'alignments'; use only 'unmatched_sentences' for a semantic-unmatched result."
        )
    if "alignments" not in document:
        _raise_model_validation_issues("citation alignment", issues)

    rows = document["alignments"]
    if not isinstance(rows, list):
        issues.append(
            f"alignments — Problem: expected a list, received {type(rows).__name__}. Required fix: return one row per supplied sentence in report order."
        )
        _raise_model_validation_issues("citation alignment", issues)

    expected_ids = [row["sentence_id"] for row in sentences]
    sentence_domains = {row["sentence_id"]: row["domain"] for row in sentences}
    same_domain_fact_ids = {
        domain: [fact_id for fact_id, fact in facts.items() if fact["domain"] == domain]
        for domain in DOMAINS
    }
    actual_ids = []
    valid_rows = []
    for index, row in enumerate(rows, start=1):
        location = f"alignments[{index - 1}]"
        expected_sentence_id = expected_ids[index - 1] if index <= len(expected_ids) else None
        if not isinstance(row, dict):
            issues.append(
                f"{location} — Problem: expected an object, received {row!r}. Required fix: return exactly sentence_id and fact_ids."
            )
            continue
        expected_fields = {"sentence_id", "fact_ids"}
        missing = sorted(expected_fields - set(row))
        unexpected = sorted(set(row) - expected_fields)
        if missing:
            issues.append(f"{location} — Problem: missing field(s): {', '.join(missing)}. Required fix: add them.")
        if unexpected:
            issues.append(
                f"{location} — Problem: unexpected field(s): {', '.join(unexpected)}. Required fix: remove them; only sentence_id and fact_ids are allowed."
            )
        sentence_id = row.get("sentence_id")
        fact_ids = row.get("fact_ids")
        valid_sentence_id = isinstance(sentence_id, str) and bool(sentence_id.strip())
        if "sentence_id" in row and not valid_sentence_id:
            fix = f"set sentence_id to {expected_sentence_id!r}" if expected_sentence_id else "use the exact supplied sentence_id for this row"
            issues.append(
                f"{location}.sentence_id — Problem: expected a non-empty string, received {sentence_id!r}. Required fix: {fix}."
            )
        if valid_sentence_id:
            actual_ids.append(sentence_id)
        valid_fact_ids = isinstance(fact_ids, list) and bool(fact_ids)
        fact_strings = []
        if "fact_ids" in row:
            if not isinstance(fact_ids, list):
                issues.append(
                    f"{location}.fact_ids — Problem: expected a non-empty list, received {type(fact_ids).__name__}. "
                    "Required fix: return one or more exact supplied fact_id strings from the same domain."
                )
                valid_fact_ids = False
            elif not fact_ids:
                domain = sentence_domains.get(sentence_id)
                allowed = same_domain_fact_ids.get(domain, []) if domain else []
                issues.append(
                    f"{location}.fact_ids — Problem: list is empty. Required fix: supply one or more same-domain fact IDs"
                    + (f"; allowed here: {allowed!r}." if allowed else ".")
                )
                valid_fact_ids = False
            else:
                seen = set()
                for fact_index, fact_id in enumerate(fact_ids):
                    if not isinstance(fact_id, str) or not fact_id.strip():
                        issues.append(
                            f"{location}.fact_ids[{fact_index}] — Problem: expected a non-empty fact_id string, received {fact_id!r}. "
                            "Required fix: replace it with an exact supplied same-domain fact_id."
                        )
                        valid_fact_ids = False
                        continue
                    fact_strings.append(fact_id)
                    if fact_id in seen:
                        issues.append(
                            f"{location}.fact_ids[{fact_index}] — Problem: duplicate fact_id {fact_id!r}. Required fix: list each fact_id once."
                        )
                        valid_fact_ids = False
                    else:
                        seen.add(fact_id)
        if valid_sentence_id and isinstance(fact_ids, list) and fact_strings:
            # Continue semantic checks even when the same row also has duplicate or malformed fact IDs,
            # so one retry receives every independently detectable repair.
            valid_rows.append((index, sentence_id, fact_strings))

    counts = {sentence_id: actual_ids.count(sentence_id) for sentence_id in set(actual_ids)}
    missing_ids = [sentence_id for sentence_id in expected_ids if counts.get(sentence_id, 0) == 0]
    duplicate_ids = [sentence_id for sentence_id in expected_ids if counts.get(sentence_id, 0) > 1]
    unexpected_ids = [sentence_id for sentence_id in actual_ids if sentence_id not in sentence_domains]
    if missing_ids:
        issues.append(
            f"alignments — Problem: missing sentence_id(s): {missing_ids!r}. Required fix: add exactly one row for each missing sentence in report order."
        )
    if duplicate_ids:
        issues.append(
            f"alignments — Problem: duplicate sentence_id(s): {duplicate_ids!r}. Required fix: keep exactly one row for each supplied sentence_id."
        )
    if unexpected_ids:
        issues.append(
            f"alignments — Problem: unknown sentence_id(s): {unexpected_ids!r}. Required fix: remove them and use only supplied sentence IDs."
        )
    if actual_ids != expected_ids:
        issues.append(
            f"alignments — Problem: sentence IDs are not exactly once in report order. Expected {expected_ids!r}; received {actual_ids!r}. "
            "Required fix: return the rows in the exact expected sequence."
        )

    for row_index, sentence_id, fact_ids in valid_rows:
        if sentence_id not in sentence_domains:
            continue
        domain = sentence_domains[sentence_id]
        allowed = same_domain_fact_ids.get(domain, [])
        for fact_id in fact_ids:
            if fact_id not in facts:
                issues.append(
                    f"alignments[{row_index - 1}].fact_ids — Problem: {fact_id!r} is not a supplied fact_id. "
                    f"Required fix: remove it and use only same-domain fact IDs; allowed here: {allowed!r}."
                )
            elif facts[fact_id]["domain"] != domain:
                issues.append(
                    f"alignments[{row_index - 1}].fact_ids — Problem: {fact_id!r} is a cross-domain fact for sentence {sentence_id!r}. "
                    f"Required fix: use only {domain} fact IDs; allowed here: {allowed!r}."
                )
    _raise_model_validation_issues("citation alignment", issues)
    alignment = {row["sentence_id"]: list(row["fact_ids"]) for row in rows}
    return sentences, facts, alignment


def _sentence_fact_alignment_validator(work: Path, path: Path) -> str:
    if _unmatched_summary_feedback(work, path) is not None:
        return "summary sentence unmatched"
    _load_sentence_fact_alignment(work, path)
    return "sentence-to-fact citation alignment validated"


def _unmatched_summary_feedback(work: Path, path: Path) -> str | None:
    text = _read(path).strip()
    if text == "UNMATCHED_SUMMARY_SENTENCE":
        raise ValueError(
            "unmatched sentence result failed validation with 1 issue(s):\n"
            "1. Top level — Problem: bare UNMATCHED_SUMMARY_SENTENCE provides no sentence or repair reason. "
            "Required fix: return unmatched_sentences YAML with each unmatched supplied sentence_id, its exact supplied sentence text, and a non-empty actionable reason."
        )
    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if not isinstance(document, dict) or "unmatched_sentences" not in document:
        return None
    issues = []
    if set(document) != {"unmatched_sentences"}:
        unexpected = sorted(set(document) - {"unmatched_sentences"})
        missing_text = ""
        if unexpected:
            missing_text = f" Unexpected field(s): {', '.join(unexpected)}."
        issues.append(
            "Top level — Problem: an unmatched result must contain exactly unmatched_sentences." + missing_text +
            " Required fix: remove every other top-level field."
        )
    rows = document["unmatched_sentences"]
    if not isinstance(rows, list):
        issues.append(
            f"unmatched_sentences — Problem: expected a non-empty list, received {type(rows).__name__}. "
            "Required fix: return one detail row for each unmatched report sentence."
        )
        _raise_model_validation_issues("unmatched sentence result", issues)
    if not rows:
        issues.append(
            "unmatched_sentences — Problem: list is empty. Required fix: if nothing is unmatched, return alignments; otherwise include each unmatched sentence detail."
        )

    manifest = _summary_sentence_manifest(_read(work / "report-draft.md"))
    by_id = {row["sentence_id"]: row for row in manifest}
    seen = set()
    feedback = []
    for index, row in enumerate(rows, start=1):
        location = f"unmatched_sentences[{index - 1}]"
        if not isinstance(row, dict):
            issues.append(
                f"{location} — Problem: expected an object, received {row!r}. Required fix: return exactly sentence_id, sentence and reason."
            )
            continue
        expected_fields = {"sentence_id", "sentence", "reason"}
        missing = sorted(expected_fields - set(row))
        unexpected = sorted(set(row) - expected_fields)
        if missing:
            issues.append(f"{location} — Problem: missing field(s): {', '.join(missing)}. Required fix: add them.")
        if unexpected:
            issues.append(
                f"{location} — Problem: unexpected field(s): {', '.join(unexpected)}. Required fix: remove them; only sentence_id, sentence and reason are allowed."
            )
        values = {}
        for key in expected_fields:
            if key not in row:
                continue
            value = row[key]
            if not isinstance(value, str) or not value.strip():
                issues.append(
                    f"{location}.{key} — Problem: blank or not a string ({value!r}). Required fix: provide a non-empty string."
                )
            else:
                values[key] = value
        sentence_id = values.get("sentence_id")
        if sentence_id:
            if sentence_id in seen:
                issues.append(
                    f"{location}.sentence_id — Problem: duplicate unmatched sentence {sentence_id!r}. Required fix: report each unmatched sentence once."
                )
            else:
                seen.add(sentence_id)
            if sentence_id not in by_id:
                issues.append(
                    f"{location}.sentence_id — Problem: {sentence_id!r} is not a supplied report sentence ID. "
                    f"Required fix: use one exact supplied ID: {list(by_id)!r}."
                )
            elif "sentence" in values and values["sentence"] != by_id[sentence_id]["sentence"]:
                issues.append(
                    f"{location}.sentence — Problem: text does not exactly match supplied {sentence_id!r}. "
                    f"Expected {by_id[sentence_id]['sentence']!r}; received {values['sentence']!r}. Required fix: copy the supplied sentence text exactly."
                )
        if all(key in values for key in expected_fields):
            feedback.append(f"- {values['sentence_id']}: {values['sentence']}\n  Reason: {values['reason']}")
    _raise_model_validation_issues("unmatched sentence result", issues)
    return "\n".join(feedback)


def _assemble_cited_report(work: Path, alignment_path: Path) -> Path:
    draft = _read(work / "report-draft.md")
    sentences, facts, alignment = _load_sentence_fact_alignment(work, alignment_path)
    parts = []
    cursor = 0
    for sentence in sentences:
        end = sentence["end"]
        parts.append(draft[cursor:end])
        tags = []
        for fact_id in alignment[sentence["sentence_id"]]:
            citation = facts[fact_id]["citation"]
            if citation:
                for tag in RUNTIME_CARD_TAG_RE.findall(citation):
                    if tag not in tags:
                        tags.append(tag)
        disposition = "".join(f"[card:{tag}]" for tag in tags) if tags else "(no citation required)"
        parts.append(" " + disposition)
        cursor = end
    parts.append(draft[cursor:])
    output = work / "report-cited.md"
    _atomic_write(output, "".join(parts))
    return output


def _citation_alignment_validator(work: Path, path: Path) -> str:
    text = _read(path)
    if text.strip() == "UNMATCHED_SUMMARY_SENTENCE":
        return "summary sentence unmatched"
    draft = _read(work / "report-draft.md")
    if _plain_from_cited(text).strip() != draft.strip():
        raise ValueError("final citation alignment changed report prose instead of only adding citation dispositions")
    runtime.validate_cited_report(work)
    return "final citation alignment validated"


def _final_alignment_validator(work: Path, alignment_path: Path) -> str:
    feedback = _unmatched_summary_feedback(work, alignment_path)
    if feedback is not None:
        return "summary sentence unmatched"
    _load_sentence_fact_alignment(work, alignment_path)
    cited = _assemble_cited_report(work, alignment_path)
    try:
        return _citation_alignment_validator(work, cited)
    except (ValueError, OSError, KeyError) as exc:
        cited.unlink(missing_ok=True)
        raise StepFailure(
            "deterministic cited-report assembly failed after the model's sentence-to-fact alignment had already "
            "passed validation. This is not repairable by changing the alignment model output. "
            f"Internal invariant failure: {exc}"
        ) from exc


def step_6(work: Path, profile: str | None) -> int:
    runtime.facts_only(work)
    runtime.prepare_combined_evidence(work)
    max_summary_cycles = 2
    summary_feedback = None
    for cycle in range(1, max_summary_cycles + 1):
        draft = work / "report-draft.md"
        if not draft.is_file():
            suffix = ""
            if summary_feedback:
                suffix = (
                    "\n\n## Required correction from the previous citation-alignment pass\n\n"
                    "Rewrite the complete report so every sentence is directly represented by accepted facts. "
                    "Correct each reported sentence without adding outside assertions:\n\n"
                    + summary_feedback
                )
            messages = [
                {"role": "system", "content": model_client.SYSTEM_PROMPT},
                {"role": "user", "content": _read(PROMPTS / "final_summary.md") + suffix + "\n\n## Accepted facts only\n\n" + _read(work / "report-facts.yaml")},
            ]
            _model_call(work, call_id=f"summary-{cycle}", role="summarisation", messages=messages, output=draft, validator=_summary_validator, profile=profile)
        alignment = work / "report-citation-alignment.yaml"
        if not alignment.is_file():
            messages = [
                {"role": "system", "content": model_client.SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        _read(PROMPTS / "final_citation_alignment.md")
                        + "\n\n## Sentence and accepted-fact manifest\n\n```yaml\n"
                        + _citation_alignment_input(work, _read(draft))
                        + "```\n"
                    ),
                },
            ]
            _model_call(
                work,
                call_id=f"final-citations-{cycle}",
                role="final_citation_alignment",
                messages=messages,
                output=alignment,
                validator=lambda path: _final_alignment_validator(work, path),
                profile=profile,
            )
        summary_feedback = _unmatched_summary_feedback(work, alignment)
        if summary_feedback is not None:
            alignment.unlink(missing_ok=True)
            draft.rename(work / f"report-draft-unmatched-{cycle}.md")
            continue
        runtime.render_final(work)
        return EXIT_OK
    raise StepFailure("summary remained semantically unmatched to accepted facts after two synthesis cycles")


def package_bundles(work: Path, output: Path | None = None) -> Path | None:
    root = work / BUNDLE_DIR
    if not root.is_dir():
        return None
    files = sorted(p for p in root.rglob("*") if p.is_file())
    if not files:
        return None
    output = output or work / BUNDLE_ZIP
    with zipfile.ZipFile(output, "w") as zf:
        for path in files:
            info = zipfile.ZipInfo(str(path.relative_to(work)), ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes())
    return output


def step_7(work: Path) -> int:
    from scripts import package_run
    debug = work / "ngs-report-debug.zip"
    package_run.package_run_bundle(work, debug)
    print(debug)
    bundles = package_bundles(work)
    if bundles:
        print(bundles)
    _print_usage(work)
    return EXIT_OK


def run_setup(args: argparse.Namespace) -> int:
    from scripts.setup_workflow import setup_workflow

    configured_model, configured_terrace = configured_profiles()
    registry = model_registry.load_registry()
    model_profile = model_registry.resolve_profile(
        args.model_profile or configured_model, None, registry
    )
    for role in registry["roles"]:
        model_registry.resolve(role, model_profile, None, registry)
    config = runtime.load_questions()
    terrace_profile = (
        args.terrace_profile
        or configured_terrace
        or config["default_execution_profile"]
    )
    if terrace_profile not in config["execution_profiles"]:
        raise StepFailure(
            f"unknown terrace profile {terrace_profile!r}; choose one of: " + ", ".join(config["execution_profiles"])
        )
    work, demo_case, demo_expected = setup_workflow(
        workflow=WORKFLOW_ID,
        mode=args.mode,
        work_dir=args.work_dir,
        project=args.project,
        example=args.example,
        case_id=args.case_id,
    )
    write_workflow_state(work, WORKFLOW_ID, args.mode, model_profile=model_profile)
    source = work / "case-source.md"
    if args.case_file:
        supplied = args.case_file.expanduser().resolve()
        if not supplied.is_file():
            raise StepFailure(f"--case-file not found: {supplied}")
        shutil.copyfile(supplied, source)
    elif args.mode == "nel-demo" and demo_case:
        shutil.copyfile(demo_case, source)
    elif (work / "case.md").is_file():
        shutil.copyfile(work / "case.md", source)
    _save_run_state(
        work,
        {
            "schema_version": 1,
            "terrace_profile": terrace_profile,
            "model_profile": model_profile,
            "mode": args.mode,
            "validation_case": args.case_id,
        },
    )
    if args.project:
        _write_project_pointer(work)
    print(work)
    if demo_case:
        print(demo_case.relative_to(REPO_ROOT))
        print(demo_expected.relative_to(REPO_ROOT))
    print(f"MODEL_PROFILE={model_profile}")
    print(f"TERRACE_PROFILE={terrace_profile}")
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
        _atomic_write(
            SETTINGS_PATH,
            json.dumps(settings, indent=2, ensure_ascii=False) + "\n",
        )
        configured_model, configured_terrace = model_profile, terrace_profile

    effective_model = model_registry.resolve_profile(configured_model, None, registry)
    effective_terrace = configured_terrace or questions["default_execution_profile"]
    print(f"MODEL_PROFILE={effective_model}")
    print(f"TERRACE_PROFILE={effective_terrace}")
    return EXIT_OK


def run_step(step_id: str, work: Path, profile: str | None) -> int:
    _require_work(work)
    mapping = {
        "1a": lambda: step_1a(work, profile),
        "1b": lambda: step_1b(work, profile),
        "2": lambda: step_2(work),
        "3": lambda: step_3(work, profile),
        "4": lambda: step_4(work, profile),
        "5": lambda: step_5(work, profile),
        "6": lambda: step_6(work, profile),
        "7": lambda: step_7(work),
    }
    try:
        description = STEP_DESCRIPTIONS[step_id]
        display = step_id if step_id not in {"1a", "1b"} else f"1{step_id[-1]}"
        print(f"Step {display} of 7 — {description}", file=sys.stderr)
        code = mapping[step_id]()
        status = "not required" if code == EXIT_NOT_REQUIRED else "complete"
        print(f"Step {display} of 7 — {status}", file=sys.stderr)
        return code
    except KeyError as exc:
        raise StepFailure("unknown step; canonical order: 1a 1b 2 3 4 5 6 7") from exc


def run_all(work: Path, profile: str | None) -> int:
    mode = _require_work(work).get("mode")
    for step_id in ("1a", "1b", "2", "3", "4", "5", "6", "7"):
        if step_id == "1a" and mode in {"nel-validate", "nel-validate-function"}:
            continue
        code = run_step(step_id, work, profile)
        if code not in {EXIT_OK, EXIT_NOT_REQUIRED}:
            return code
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("step_id", nargs="?")
    p.add_argument("provider_model_profile", nargs="?")
    p.add_argument("provider_terrace_profile", nargs="?")
    p.add_argument("--all", action="store_true")
    p.add_argument("--work-dir", type=Path)
    p.add_argument("--project", action="store_true")
    p.add_argument("--profile")
    p.add_argument("--mode")
    p.add_argument("--example", type=int)
    p.add_argument("--case-id")
    p.add_argument("--case-file", type=Path)
    p.add_argument("--model-profile")
    p.add_argument("--terrace-profile")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.step_id == "provider":
            return run_provider(
                args.provider_model_profile, args.provider_terrace_profile
            )
        if args.provider_model_profile or args.provider_terrace_profile:
            raise StepFailure(
                "extra positional arguments are valid only for the provider command"
            )
        if args.step_id == "setup":
            if not args.mode:
                raise StepFailure("setup requires --mode")
            return run_setup(args)
        work = resolve_work_dir(args.work_dir)
        if args.step_id == "profile":
            state = _load_run_state(work)
            print(f"model_profile: {state['model_profile']}")
            print(f"terrace_profile: {state['terrace_profile']}")
            return EXIT_OK
        if args.step_id == "package-bundles":
            result = package_bundles(work)
            print(result or "no model bundles")
            return EXIT_OK
        if args.all:
            return run_all(work, args.profile)
        if not args.step_id:
            raise StepFailure("supply a step ID or --all")
        return run_step(args.step_id, work, args.profile)
    except Handoff as handoff:
        print(f"HANDOFF={handoff.call_id}")
        print(f"PROMPT={handoff.prompt}")
        print(f"OUTPUT={handoff.output}")
        return EXIT_HANDOFF
    except (StepFailure, ValueError, OSError, KeyError) as exc:
        print(f"step failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
