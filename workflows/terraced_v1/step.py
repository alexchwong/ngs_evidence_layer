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
        return {"semantic_review_cycles": 2, "structural_attempts": 3, "token_budget": 120000}
    return doc


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
    root = work / BUNDLE_DIR / call_id
    root.mkdir(parents=True, exist_ok=True)
    return root, root / "prompt.md", root / "messages.json"


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
    attempts = int(load_settings().get("structural_attempts", 3))

    # A self handoff resumes by validating the already-authored target.
    if binding.is_self:
        validator_error = None
        if output.is_file():
            try:
                message = validator(output)
                _atomic_write(root / "validated.txt", message + "\n")
                return message
            except (ValueError, OSError, KeyError) as exc:
                validator_error = str(exc)
        _atomic_write(messages_path, json.dumps(messages, indent=2, ensure_ascii=False) + "\n")
        _atomic_write(prompt_path, _render_bundle(call_id, messages, output, validator_error))
        raise Handoff(call_id, prompt_path, output)

    last_error = ""
    previous = None
    for attempt in range(1, attempts + 1):
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
            raw = model_client.complete_messages(binding, call_messages)
        except model_client.TruncatedCompletion as exc:
            previous = exc.content
            last_error = str(exc)
            continue
        except RuntimeError as exc:
            raise StepFailure(str(exc)) from exc
        text = model_client.strip_code_fence(raw)
        _atomic_write(root / f"attempt-{attempt}.output", text)
        previous_existing = output.read_text(encoding="utf-8") if output.is_file() else None
        _atomic_write(output, text)
        try:
            message = validator(output)
        except (ValueError, OSError, KeyError) as exc:
            last_error = str(exc)
            previous = text
            if previous_existing is None:
                output.unlink(missing_ok=True)
            else:
                _atomic_write(output, previous_existing)
            continue
        _atomic_write(root / "validated.txt", message + "\n")
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
    for domain in DOWNSTREAM:
        category = work / f"category-{domain}.yaml"
        if category.is_file():
            runtime.validate_category_answer(category, domain, final=True, aligned=True)
            continue
        retrieval.downstream(work, domain)
        runtime.render_evidence(work, domain)
        run_terraces(work, domain, profile)
        semantic_review_and_repair(work, domain, profile)
        evidence_alignment(work, domain, profile)
    return EXIT_OK


def _summary_validator(path: Path) -> str:
    text = _read(path).strip()
    if not text:
        raise ValueError("summary is empty")
    if "[card:" in text or "## References" in text or "(no citation required)" in text:
        raise ValueError("uncited summary must not contain citation syntax or bibliography")
    return "uncited report draft validated"


def _plain_from_cited(text: str) -> str:
    text = re.sub(r"\. (?:\[card:[0-9a-f]{6}\])+(?=\s|$)", ".", text)
    text = re.sub(r"\. \(no citation required\)(?=\s|$)", ".", text)
    return text


def _citation_alignment_validator(work: Path, path: Path) -> str:
    text = _read(path)
    if text.strip() == "UNMATCHED_SUMMARY_SENTENCE":
        return "summary sentence unmatched"
    draft = _read(work / "report-draft.md")
    if _plain_from_cited(text).strip() != draft.strip():
        raise ValueError("final citation alignment changed report prose instead of only adding citation dispositions")
    runtime.validate_cited_report(work)
    return "final citation alignment validated"


def step_6(work: Path, profile: str | None) -> int:
    runtime.facts_only(work)
    runtime.prepare_combined_evidence(work)
    max_summary_cycles = 2
    for cycle in range(1, max_summary_cycles + 1):
        draft = work / "report-draft.md"
        if not draft.is_file():
            suffix = "" if cycle == 1 else "\n\nA previous summary introduced a sentence that could not be matched to any accepted fact. Ensure every sentence is directly represented by the supplied facts."
            messages = [
                {"role": "system", "content": model_client.SYSTEM_PROMPT},
                {"role": "user", "content": _read(PROMPTS / "final_summary.md") + suffix + "\n\n## Accepted facts only\n\n" + _read(work / "report-facts.yaml")},
            ]
            _model_call(work, call_id=f"summary-{cycle}", role="summarisation", messages=messages, output=draft, validator=_summary_validator, profile=profile)
        cited = work / "report-cited.md"
        if not cited.is_file():
            messages = [
                {"role": "system", "content": model_client.SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        _read(PROMPTS / "final_citation_alignment.md")
                        + "\n\n## Uncited report\n\n"
                        + _read(draft)
                        + "\n\n## Accepted fact/reason/citation states\n\n"
                        + runtime.accepted_categories_document(work)
                    ),
                },
            ]
            _model_call(
                work,
                call_id=f"final-citations-{cycle}",
                role="final_citation_alignment",
                messages=messages,
                output=cited,
                validator=lambda path: _citation_alignment_validator(work, path),
                profile=profile,
            )
        if _read(cited).strip() == "UNMATCHED_SUMMARY_SENTENCE":
            cited.unlink(missing_ok=True)
            draft.rename(work / f"report-draft-unmatched-{cycle}.md")
            continue
        _citation_alignment_validator(work, cited)
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
    return EXIT_OK


def run_setup(args: argparse.Namespace) -> int:
    from scripts.setup_workflow import setup_workflow

    registry = model_registry.load_registry()
    model_profile = model_registry.resolve_profile(args.model_profile, None, registry)
    for role in registry["roles"]:
        model_registry.resolve(role, model_profile, None, registry)
    config = runtime.load_questions()
    terrace_profile = args.terrace_profile or config["default_execution_profile"]
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
        return mapping[step_id]()
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
