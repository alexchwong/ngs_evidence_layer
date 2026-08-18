#!/usr/bin/env python3
"""Uniform front end for every categorical-v1 workflow step.

Exit codes are the interface. Any caller -- a model reading SKILL.md, a shell
script, CI -- branches on these four:

    0   step completed and validated
    1   deterministic failure
    10  handoff: the role is bound to the session model. A prompt bundle has
        been written; complete the output file and re-invoke with --complete.
    20  step not required in this run. The category manifest forbids a model
        call for this step. Continue to the next step.

Usage:
    step.py setup --mode <mode> [--example N | --case-id ID]
                  [--work-dir DIR | --project] [--case-file FILE]
                  [--model-profile PROFILE]
    step.py <step-id> [--work-dir DIR] [--profile P] [--complete] [--max-attempts N]
    step.py --all [--work-dir DIR] [--profile P]
    step.py package-bundles [--work-dir DIR]
    step.py profile [--work-dir DIR] [--profile P]
    step.py settings

Override the settings file for one invocation with NEL_STEP_SETTINGS=<path>.
For commands that need a work directory, resolution order is explicit
--work-dir, NEL_WORK_DIR, then the current project selected by setup --project.

Per-step retry counts and truncation-recovery behaviour are read from
workflows/categorical_v1/settings.json (not models.json, which is the model
registry). --max-attempts on the command line overrides the file for that
invocation only.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import os
import shutil
import sys
import zipfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.workflow_registry import read_workflow_state, write_workflow_state  # noqa: E402
from workflows.categorical_v1 import model_client, model_registry, model_steps  # noqa: E402

WORKFLOW_ID = "categorical-v1"
BUNDLE_DIR = ".model-steps"
BUNDLE_ZIP = "ngs-report-model-steps.zip"
SETTINGS_PATH = Path(__file__).resolve().parent / "settings.json"
SETTINGS_TEMPLATE_PATH = Path(__file__).resolve().parent / "settings.json.template"
PROJECT_ROOT = REPO_ROOT / "temp"
PROJECT_POINTER = PROJECT_ROOT / ".categorical-v1-project"
WORK_DIR_ENV = "NEL_WORK_DIR"

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_HANDOFF = 10
EXIT_NOT_REQUIRED = 20

ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

_DEFAULT_SETTINGS = {
    "schema_version": 1,
    "max_attempts": {"default": 3},
    "max_tokens_growth_on_truncation": 1.5,
    "max_tokens_ceiling": 32768,
}


SETTINGS_ENV = "NEL_STEP_SETTINGS"


def load_settings(path: Path | None = None) -> dict:
    """Runtime-tunable settings, separate from the model registry.

    Resolution: explicit path, then NEL_STEP_SETTINGS, then the workflow-local
    settings.json. Missing or unreadable falls back to built-in defaults rather
    than failing -- this file is a convenience knob, not part of the enforced
    permitted-input contract.
    """
    if path is None:
        override = os.environ.get(SETTINGS_ENV, "").strip()
        path = Path(override) if override else SETTINGS_PATH
        if not override and not path.is_file():
            path = SETTINGS_TEMPLATE_PATH
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(_DEFAULT_SETTINGS)
    if not isinstance(data, dict) or data.get("schema_version") != 1:
        return dict(_DEFAULT_SETTINGS)
    return data


def _max_attempts_for(step_id: str, settings: dict, override: int | None) -> int:
    if override is not None:
        attempts = override
    else:
        table = settings.get("max_attempts") or {}
        attempts = int(table.get(step_id, table.get("default", 3)))
    if attempts < 1:
        raise StepFailure(f"max attempts for step {step_id} must be at least 1; found {attempts}")
    return attempts


class StepFailure(RuntimeError):
    """A deterministic failure that should surface as exit 1."""


# ---------------------------------------------------------------------------
# Work-directory helpers
# ---------------------------------------------------------------------------


def _require_categorical(work: Path) -> dict:
    state = read_workflow_state(work)
    if state.get("workflow_id") != WORKFLOW_ID:
        raise StepFailure(
            f"work directory {work} is bound to workflow {state.get('workflow_id')!r}. "
            f"This driver only executes {WORKFLOW_ID}."
        )
    return state


def _bundle_dir(work: Path, step_id: str) -> Path:
    path = Path(work) / BUNDLE_DIR / step_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_write(path: Path, text: str) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)
    return path


def _write_project_pointer(work: Path) -> None:
    """Persist the current repository-local project selected by setup --project."""
    work = Path(work).resolve()
    project_root = PROJECT_ROOT.resolve()
    if not work.is_relative_to(project_root):
        raise StepFailure(f"project work directory must be under {project_root}: {work}")
    _atomic_write(PROJECT_POINTER, str(work) + "\n")


def _validated_implicit_work_dir(path: Path, *, source: str) -> Path:
    work = Path(path).expanduser().resolve()
    if not work.is_dir():
        raise StepFailure(f"{source} points to a missing work directory: {work}")
    state = read_workflow_state(work)
    if state.get("workflow_id") != WORKFLOW_ID:
        raise StepFailure(
            f"{source} points to workflow {state.get('workflow_id')!r}, not {WORKFLOW_ID!r}: {work}"
        )
    return work


def resolve_cli_work_dir(explicit: Path | None) -> Path:
    """Resolve explicit path, shell override, then the current project pointer."""
    if explicit is not None:
        return Path(explicit).expanduser().resolve()

    environment = os.environ.get(WORK_DIR_ENV, "").strip()
    if environment:
        return _validated_implicit_work_dir(Path(environment), source=WORK_DIR_ENV)

    if PROJECT_POINTER.is_file():
        recorded = PROJECT_POINTER.read_text(encoding="utf-8").strip()
        if not recorded:
            raise StepFailure(f"project pointer is blank: {PROJECT_POINTER}")
        work = (PROJECT_ROOT / recorded).expanduser().resolve()
        if not work.is_relative_to(PROJECT_ROOT.resolve()):
            raise StepFailure(f"project pointer escapes repository temp directory: {work}")
        return _validated_implicit_work_dir(work, source=str(PROJECT_POINTER))

    raise StepFailure(
        f"--work-dir is required unless {WORK_DIR_ENV} is set or setup --project has selected "
        f"a current project in {PROJECT_POINTER}"
    )


# ---------------------------------------------------------------------------
# Bundle construction
# ---------------------------------------------------------------------------


def _error_hint(error: str) -> str:
    """Targeted guidance for failure modes a bare validator string does not explain."""
    lowered = error.lower()
    hints: list[str] = []
    if "invalid yaml" in lowered or "mapping values are not allowed" in lowered:
        hints.append(
            "This is a YAML syntax error, not a content error. A scalar value containing "
            "a colon followed by a space, or a leading '-', '?', '*', '&', '{' or '[', "
            "must be wrapped in double quotes. Quote the value on the reported line and "
            "check every other value for the same construct. Do not change the clinical "
            "content while fixing this."
        )
    if "word" in lowered and "limit" in lowered:
        hints.append(
            "Shorten by removing redundancy, not by dropping a clinically distinct fact "
            "or a citation marker."
        )
    if "citation" in lowered or "card:" in lowered:
        hints.append(
            "Citation markers must be reproduced exactly as they appear in the evidence "
            "file. Do not invent, renumber or reformat them."
        )
    return "\n".join(hints)


def build_bundle(
    step: model_steps.ModelStep,
    work: Path,
    *,
    validator_error: str | None = None,
    previous_output: str | None = None,
) -> str:
    """Render the complete permitted input set for one model step.

    When `previous_output` is supplied the bundle asks for a targeted revision of
    that text rather than a fresh draft. Regenerating from scratch does not fix a
    mechanical defect the model is disposed to repeat.
    """
    work = Path(work)
    heading = f"# Model step {step.step_id} — {step.title}"
    if previous_output is not None:
        heading += " (revision)"
    sections: list[str] = [heading, ""]

    for prompt in model_steps.prompt_sequence(step):
        if not prompt.is_file():
            raise StepFailure(f"step {step.step_id} declares a missing prompt file: {prompt}")
        relative = prompt.relative_to(REPO_ROOT)
        sections.append(f'<instructions path="{relative}">')
        sections.append(prompt.read_text(encoding="utf-8").rstrip())
        sections.append("</instructions>")
        sections.append("")

    for source in step.inputs(work):
        source = Path(source)
        if not source.is_file():
            raise StepFailure(
                f"step {step.step_id} declares input {source} but the file does not exist. "
                "Run the preceding step; do not proceed with a partial input set."
            )
        sections.append(f'<input path="{source.name}">')
        sections.append(source.read_text(encoding="utf-8").rstrip())
        sections.append("</input>")
        sections.append("")

    output_path = step.output_path(work)
    if previous_output is not None:
        sections.append(f'<previous-attempt path="{step.output}">')
        sections.append(previous_output.rstrip())
        sections.append("</previous-attempt>")
        sections.append("")
    elif step.seed_output:
        if not output_path.is_file():
            raise StepFailure(
                f"step {step.step_id} expects the deterministic template {output_path} "
                "to exist before drafting. Run the preceding deterministic step."
            )
        sections.append(f'<document-to-complete path="{step.output}">')
        sections.append(output_path.read_text(encoding="utf-8").rstrip())
        sections.append("</document-to-complete>")
        sections.append("")

    if validator_error:
        sections.append("<validator-error>")
        sections.append(validator_error.strip())
        hint = _error_hint(validator_error)
        if hint:
            sections.append("")
            sections.append(hint)
        sections.append("</validator-error>")
        sections.append("")

    if previous_output is not None:
        sections.append(
            "The previous attempt shown above failed the deterministic validator with "
            "the error(s) shown. Repair every defect listed inside <validator-error> in "
            "this one revision. Preserve fields not implicated by a listed defect, "
            "including every rule ID, valid statement, valid citation marker and the "
            "existing ordering. Before returning, scan the complete output and confirm "
            "that none of the listed defects remains."
        )
        sections.append("")
        sections.append(f"Output the complete corrected content of `{step.output}` only.")
    else:
        sections.append(f"Output the complete content of `{step.output}` only.")
    sections.append("")
    return "\n".join(sections)


def _write_bundle(step, work: Path, text: str, attempt: int | None = None) -> Path:
    name = "prompt.md" if attempt is None else f"prompt-attempt-{attempt}.md"
    return _atomic_write(_bundle_dir(work, step.step_id) / name, text)


# ---------------------------------------------------------------------------
# Model step execution
# ---------------------------------------------------------------------------


def _last_error_path(work: Path, step_id: str) -> Path:
    return Path(work) / BUNDLE_DIR / step_id / "last-error.txt"


def _read_last_error(work: Path, step_id: str) -> str | None:
    path = _last_error_path(work, step_id)
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8").strip()
    return text or None


def _record_last_error(work: Path, step_id: str, error: str) -> None:
    _atomic_write(_last_error_path(work, step_id), error.strip() + "\n")


def _clear_last_error(work: Path, step_id: str) -> None:
    _last_error_path(work, step_id).unlink(missing_ok=True)


def _check_required(step: model_steps.ModelStep, work: Path) -> tuple[bool, str]:
    if step.required is None:
        return True, ""
    return step.required(work)


def run_model_step(
    step: model_steps.ModelStep,
    work: Path,
    *,
    profile: str | None,
    complete: bool,
    max_attempts: int | None,
) -> int:
    work = Path(work)
    state = _require_categorical(work)
    mode = state.get("mode")

    if step.modes is not None and mode not in step.modes:
        raise StepFailure(
            f"step {step.step_id} is not permitted in mode {mode!r}. "
            f"Permitted modes: {', '.join(step.modes)}."
        )

    required, reason = _check_required(step, work)
    if not required:
        print(f"NOT_REQUIRED step={step.step_id}")
        if reason:
            print(f"REASON={reason}")
        return EXIT_NOT_REQUIRED

    if complete:
        try:
            message = step.validate(work)
        except (ValueError, KeyError, OSError) as exc:
            # Persist the error so re-invoking without --complete builds a repair
            # bundle carrying both the rejected output and the validator error.
            _record_last_error(work, step.step_id, str(exc))
            raise StepFailure(
                f"{exc}\nRe-run this command without --complete to receive a revision "
                "bundle containing your previous output and this error."
            ) from exc
        _clear_last_error(work, step.step_id)
        print(f"OK step={step.step_id} {message}")
        return EXIT_OK

    if step.prepare is not None:
        step.prepare(work)

    binding = model_registry.resolve(step.role, profile, work)

    if binding.is_self:
        pending_error = _read_last_error(work, step.step_id)
        previous_output = None
        output_path = step.output_path(work)
        if pending_error and output_path.is_file():
            previous_output = output_path.read_text(encoding="utf-8")
        bundle = build_bundle(
            step,
            work,
            validator_error=pending_error if previous_output else None,
            previous_output=previous_output,
        )
        prompt_path = _write_bundle(step, work, bundle)
        print("HANDOFF")
        print(f"STEP={step.step_id}")
        print(f"ROLE={step.role}")
        print(f"MODE={'revision' if previous_output else 'draft'}")
        print(f"PROMPT={prompt_path}")
        print(f"OUTPUT={output_path}")
        if previous_output:
            print(
                f"The previous {step.output} failed validation. Read only {prompt_path}, "
                f"revise {step.output} to correct the reported error, then re-run this "
                "command with --complete."
            )
        else:
            print(
                f"Read only {prompt_path}, write {step.output}, then re-run this command "
                "with --complete."
            )
        return EXIT_HANDOFF

    settings = load_settings()
    attempts = _max_attempts_for(step.step_id, settings, max_attempts)
    growth = float(settings.get("max_tokens_growth_on_truncation", 1.5))
    configured_ceiling = int(settings.get("max_tokens_ceiling", 32768))
    # A growth ceiling below the profile's starting cap must never reduce the
    # active response budget or make the first truncation unrecoverable. Allow
    # at least one configured growth increment from the profile's initial cap.
    minimum_growth_ceiling = int(binding.max_tokens * growth)
    ceiling = max(minimum_growth_ceiling, configured_ceiling)
    bundle_dir = _bundle_dir(work, step.step_id)
    last_error: str | None = None
    last_output: str | None = None
    active_binding = binding

    for attempt in range(1, attempts + 1):
        bundle = build_bundle(
            step, work, validator_error=last_error, previous_output=last_output
        )
        prompt_path = _write_bundle(step, work, bundle, attempt=attempt)
        kind = "revision" if last_output is not None else "draft"
        print(
            f"[{step.step_id}] attempt {attempt}/{attempts} ({kind}) model={active_binding.model} "
            f"max_tokens={active_binding.max_tokens} bundle={len(bundle)} chars -> {prompt_path.name}"
        )

        try:
            raw = model_client.complete(active_binding, model_client.SYSTEM_PROMPT, bundle)
        except model_client.TruncatedCompletion as exc:
            # The response was cut off, not wrong. Retrying the same bundle with
            # the same cap reproduces the same cutoff -- observed in practice as
            # "one more item answered per retry" while everything past the cap
            # stays blank. Raise the cap for this step's remaining attempts and
            # treat the partial text as ordinary revision material, not a
            # rejected draft, so the next attempt continues it rather than
            # re-deriving what it already got right.
            grown = min(int(active_binding.max_tokens * growth), ceiling)
            print(
                f"[{step.step_id}] attempt {attempt} truncated at max_tokens="
                f"{active_binding.max_tokens} (finish_reason=length)."
            )
            if grown <= active_binding.max_tokens:
                raise StepFailure(
                    f"step {step.step_id} is truncating at the configured ceiling "
                    f"({ceiling} tokens) and cannot be grown further. This step's output "
                    "does not fit the model's response budget. Raise max_tokens_ceiling "
                    "in settings.json, or reduce this step's input bundle."
                ) from exc
            print(f"[{step.step_id}] raising max_tokens to {grown} for the remaining attempts.")
            active_binding = dataclasses.replace(active_binding, max_tokens=grown)
            last_error = (
                "The previous response was cut off before finishing (it ran out of output "
                "space partway through). Continue it: keep everything already written and "
                "answer every remaining rule/category the input requires. Do not restart "
                "from the beginning and do not shorten earlier answers to make room."
            )
            last_output = exc.content
            continue
        except RuntimeError as exc:
            raise StepFailure(str(exc)) from exc

        text = model_client.strip_code_fence(raw)
        attempt_path = _atomic_write(bundle_dir / f"attempt-{attempt}.output", text)

        # The real output path keeps its deterministic template until an attempt
        # validates, so a failed run never leaves an unvalidated draft in place.
        output_path = step.output_path(work)
        preserved = output_path.read_text(encoding="utf-8") if output_path.is_file() else None
        _atomic_write(output_path, text)
        try:
            message = step.validate(work)
        except (ValueError, KeyError, OSError) as exc:
            last_error = str(exc)
            # Keep the rejected text so the next attempt revises it rather than
            # redrafting from scratch, which does not fix a mechanical defect.
            last_output = text
            if preserved is None:
                output_path.unlink(missing_ok=True)
            else:
                _atomic_write(output_path, preserved)
            print(f"[{step.step_id}] attempt {attempt} rejected: {last_error}")
            continue

        _clear_last_error(work, step.step_id)
        print(f"OK step={step.step_id} {message}")
        print(f"ATTEMPT={attempt_path}")
        return EXIT_OK

    raise StepFailure(
        f"step {step.step_id} failed validation on all {attempts} attempts. "
        f"Last validator error: {last_error}. Attempts are retained under "
        f"{bundle_dir} and {step.output} is unchanged."
    )


def run_deterministic_step(step: model_steps.DeterministicStep, work: Path, python: str) -> int:
    work = Path(work)
    state = _require_categorical(work)
    mode = state.get("mode")
    if step.modes is not None and mode not in step.modes:
        raise StepFailure(
            f"step {step.step_id} is not permitted in mode {mode!r}."
        )
    for line in step.run(work, python):
        print(line)
    print(f"OK step={step.step_id} {step.title}")
    return EXIT_OK


# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------


def run_setup(args: argparse.Namespace) -> int:
    from scripts.setup_workflow import setup_workflow

    registry = model_registry.load_registry()
    profile_id = model_registry.resolve_profile(args.model_profile, None, registry)
    for role in registry["roles"]:
        model_registry.resolve(role, profile_id, None, registry)

    work, demo_case, demo_expected = setup_workflow(
        workflow=WORKFLOW_ID,
        mode=args.mode,
        work_dir=args.work_dir,
        project=args.project,
        example=args.example,
        case_id=args.case_id,
    )
    write_workflow_state(work, WORKFLOW_ID, args.mode, model_profile=profile_id)

    case_source = work / "case-source.md"
    if args.case_file is not None:
        source = Path(args.case_file).expanduser().resolve()
        if not source.is_file():
            raise StepFailure(f"--case-file does not exist: {source}")
        if args.mode not in ("ngs-report", "nel-demo"):
            raise StepFailure(
                f"--case-file is not permitted in mode {args.mode!r}; setup writes case.md directly."
            )
        shutil.copyfile(source, case_source)
    elif args.mode == "nel-demo" and demo_case is not None:
        shutil.copyfile(demo_case, case_source)
    elif (work / "case.md").is_file():
        # Validation modes: step 1A does not run, but the artifact allowlist is
        # uniform across modes, so mirror the case text that setup already wrote.
        shutil.copyfile(work / "case.md", case_source)

    # Select the project only after all setup validation and file operations have
    # succeeded, so a failed setup cannot replace a known-good current project.
    if args.project:
        _write_project_pointer(work)

    print(work)
    if demo_case is not None:
        print(demo_case.relative_to(REPO_ROOT))
        print(demo_expected.relative_to(REPO_ROOT))
    print(f"MODEL_PROFILE={profile_id}")
    if args.project:
        print(f"{WORK_DIR_ENV}={work}")
    return EXIT_OK


# ---------------------------------------------------------------------------
# Bundle packaging
# ---------------------------------------------------------------------------


def package_bundles(work: Path, output: Path | None = None) -> Path | None:
    work = Path(work).resolve()
    root = work / BUNDLE_DIR
    if not root.is_dir():
        return None
    output = Path(output) if output is not None else work / BUNDLE_ZIP
    files = sorted(path for path in root.rglob("*") if path.is_file())
    if not files:
        return None
    with zipfile.ZipFile(output, "w") as archive:
        for path in files:
            info = zipfile.ZipInfo(str(path.relative_to(work)), ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    return output


# ---------------------------------------------------------------------------
# Whole-sequence runner
# ---------------------------------------------------------------------------


def run_all(
    work: Path,
    profile: str | None,
    python: str,
    max_attempts: int | None = None,
) -> int:
    work = Path(work)
    state = _require_categorical(work)
    mode = state.get("mode")
    for step_id in model_steps.steps_for_mode(mode):
        step = model_steps.get_step(step_id)
        if isinstance(step, model_steps.ModelStep):
            code = run_model_step(
                step, work, profile=profile, complete=False, max_attempts=max_attempts
            )
        else:
            code = run_deterministic_step(step, work, python)
        if code == EXIT_HANDOFF:
            print(
                f"\nStopped at step {step_id}: the resolved profile binds role "
                f"{step.role!r} to the session model, which this runner cannot provide. "
                "Re-run with a delegating profile, or execute the sequence step by step "
                "and complete each handoff.",
                file=sys.stderr,
            )
            return EXIT_HANDOFF
        if code not in (EXIT_OK, EXIT_NOT_REQUIRED):
            return code
    return EXIT_OK


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "step_id",
        nargs="?",
        help="step token, or 'setup', 'package-bundles', 'profile'. Canonical order: "
        + " ".join(model_steps.ORDER),
    )
    parser.add_argument("--all", action="store_true", help="run the whole sequence")
    parser.add_argument("--work-dir", type=Path)
    parser.add_argument("--project", action="store_true")
    parser.add_argument("--profile", help="model profile selector for this invocation")
    parser.add_argument("--complete", action="store_true", help="validate an already-written output")
    parser.add_argument("--max-attempts", type=int)
    parser.add_argument("--python", default=sys.executable)
    # setup-only
    parser.add_argument("--mode")
    parser.add_argument("--example", type=int)
    parser.add_argument("--case-id")
    parser.add_argument("--case-file", type=Path)
    parser.add_argument("--model-profile")
    parser.add_argument("--output", type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.step_id == "setup":
            if not args.mode:
                raise StepFailure("setup requires --mode")
            return run_setup(args)

        if args.all:
            work_dir = resolve_cli_work_dir(args.work_dir)
            return run_all(work_dir, args.profile, args.python, args.max_attempts)

        if args.step_id == "settings":
            settings = load_settings()
            print(f"settings file: {SETTINGS_PATH}")
            print(json.dumps(settings, indent=2))
            return EXIT_OK

        work_dir = resolve_cli_work_dir(args.work_dir)

        if args.step_id == "package-bundles":
            path = package_bundles(work_dir, args.output)
            if path is None:
                print("no model-step bundles to package")
            else:
                print(path)
            return EXIT_OK

        if args.step_id == "profile":
            registry = model_registry.load_registry()
            profile_id = model_registry.resolve_profile(args.profile, work_dir, registry)
            print(f"profile: {profile_id}")
            for role in registry["roles"]:
                print("  " + model_registry.resolve(role, profile_id, work_dir, registry).describe())
            return EXIT_OK

        if not args.step_id:
            raise StepFailure("a step token is required. Canonical order: " + " ".join(model_steps.ORDER))

        step = model_steps.get_step(args.step_id)
        if isinstance(step, model_steps.ModelStep):
            return run_model_step(
                step,
                work_dir,
                profile=args.profile,
                complete=args.complete,
                max_attempts=args.max_attempts,
            )
        if args.complete:
            raise StepFailure(f"step {args.step_id} is deterministic; --complete does not apply")
        return run_deterministic_step(step, work_dir, args.python)

    except (StepFailure, ValueError, KeyError, OSError) as exc:
        print(f"step failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
