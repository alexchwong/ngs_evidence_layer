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
    step.py <step-id> --work-dir DIR [--profile P] [--complete] [--max-attempts N]
    step.py --all --work-dir DIR [--profile P]
    step.py package-bundles --work-dir DIR
    step.py profile --work-dir DIR [--profile P]
"""
from __future__ import annotations

import argparse
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

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_HANDOFF = 10
EXIT_NOT_REQUIRED = 20

ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


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
            "the error shown. Revise that text to correct the reported defect. Change "
            "nothing else: preserve every rule ID, every retained statement, every "
            "citation marker and the existing ordering."
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

    attempts = max_attempts or step.max_attempts
    bundle_dir = _bundle_dir(work, step.step_id)
    last_error: str | None = None
    last_output: str | None = None

    for attempt in range(1, attempts + 1):
        bundle = build_bundle(
            step, work, validator_error=last_error, previous_output=last_output
        )
        prompt_path = _write_bundle(step, work, bundle, attempt=attempt)
        kind = "revision" if last_output is not None else "draft"
        print(
            f"[{step.step_id}] attempt {attempt}/{attempts} ({kind}) model={binding.model} "
            f"bundle={len(bundle)} chars -> {prompt_path.name}"
        )

        try:
            raw = model_client.complete(binding, model_client.SYSTEM_PROMPT, bundle)
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

    print(work)
    if demo_case is not None:
        print(demo_case.relative_to(REPO_ROOT))
        print(demo_expected.relative_to(REPO_ROOT))
    print(f"MODEL_PROFILE={profile_id}")
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


def run_all(work: Path, profile: str | None, python: str) -> int:
    work = Path(work)
    state = _require_categorical(work)
    mode = state.get("mode")
    for step_id in model_steps.steps_for_mode(mode):
        step = model_steps.get_step(step_id)
        if isinstance(step, model_steps.ModelStep):
            code = run_model_step(
                step, work, profile=profile, complete=False, max_attempts=None
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
            if args.work_dir is None:
                raise StepFailure("--all requires --work-dir")
            return run_all(args.work_dir, args.profile, args.python)

        if args.work_dir is None:
            raise StepFailure("--work-dir is required")

        if args.step_id == "package-bundles":
            path = package_bundles(args.work_dir, args.output)
            if path is None:
                print("no model-step bundles to package")
            else:
                print(path)
            return EXIT_OK

        if args.step_id == "profile":
            registry = model_registry.load_registry()
            profile_id = model_registry.resolve_profile(args.profile, args.work_dir, registry)
            print(f"profile: {profile_id}")
            for role in registry["roles"]:
                print("  " + model_registry.resolve(role, profile_id, args.work_dir, registry).describe())
            return EXIT_OK

        if not args.step_id:
            raise StepFailure("a step token is required. Canonical order: " + " ".join(model_steps.ORDER))

        step = model_steps.get_step(args.step_id)
        if isinstance(step, model_steps.ModelStep):
            return run_model_step(
                step,
                args.work_dir,
                profile=args.profile,
                complete=args.complete,
                max_attempts=args.max_attempts,
            )
        if args.complete:
            raise StepFailure(f"step {args.step_id} is deterministic; --complete does not apply")
        return run_deterministic_step(step, args.work_dir, args.python)

    except (StepFailure, ValueError, KeyError, OSError) as exc:
        print(f"step failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
