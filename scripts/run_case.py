#!/usr/bin/env python3
"""Thin deterministic wrapper for the case retrieval and rendering pipeline.

The only model decisions in the workflow are Step 1 (case structuring) and
Step 3 (diagnostic adjudication). This script performs the deterministic
Steps 2, 4, and 5 by invoking the canonical retrieval and rendering scripts as
subprocesses.

Usage:
  run_case.py diagnosis --work-dir <directory>
  run_case.py full --work-dir <directory>
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = REPO_ROOT / "scripts"


def resolve_work_dir(path):
    """Return an absolute, writable working directory.

    If *path* is supplied, it must resolve to a directory (creating it if
    necessary) and be writable. If not, create a retained secure system
    temporary directory.
    """
    if path:
        work = Path(path).resolve()
        if work.exists() and not work.is_dir():
            raise ValueError(f"work directory path exists but is not a directory: {work}")
        work.mkdir(parents=True, exist_ok=True)
        probe = work / ".run_case_writable"
        try:
            probe.write_text("", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            raise ValueError(f"work directory is not writable: {work}") from exc
    else:
        work = Path(tempfile.mkdtemp(prefix="ngs_evidence_layer_"))
    return work


def announce(work_dir):
    print(f"[run_case] working directory: {work_dir}", file=sys.stderr)


def run_command(command, stage):
    """Run a command array and fail closed on non-zero exit."""
    print(f"[run_case] {stage}", file=sys.stderr)
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        print(f"[run_case] {stage} failed: {exc}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as exc:
        print(f"[run_case] {stage} failed: interpreter or script not found: {exc}", file=sys.stderr)
        sys.exit(1)


def require_file(path, description):
    if not path.is_file():
        print(f"[run_case] expected output not produced: {description} ({path})", file=sys.stderr)
        sys.exit(1)


def remove_if_present(*paths):
    for path in paths:
        if path.exists():
            path.unlink()


def diagnosis(args):
    work_dir = resolve_work_dir(args.work_dir)
    announce(work_dir)

    case_input = args.case_input or (work_dir / "case-input.json")
    output = args.output or (work_dir / "diagnostic_evidence.md")

    command = [
        args.python, str(SCRIPTS / "retrieve.py"), "diagnosis",
        "--case-input", str(case_input),
        "--output", str(output),
    ]
    if args.genes:
        command.extend(["--genes", *args.genes])
    if args.provisional_disease:
        command.extend(["--provisional-disease", args.provisional_disease])
    if args.case_major_category:
        command.extend(["--case-major-category", args.case_major_category])
    if args.case_facts:
        command.extend(["--case-facts", str(args.case_facts)])
    if args.corpus:
        command.extend(["--corpus", str(args.corpus)])
    if args.index:
        command.extend(["--index", str(args.index)])

    run_command(command, "step 2: retrieve diagnosis evidence")
    require_file(output, "diagnostic_evidence.md")
    require_file(output.with_suffix(".json"), "Step-2 machine boundary")
    print(f"[run_case] output: {output}", file=sys.stderr)


def full(args):
    work_dir = resolve_work_dir(args.work_dir)
    announce(work_dir)

    diagnosis_result = args.diagnosis_result or (work_dir / "diagnostic_evidence.md")
    adjudication_result = args.adjudication_result or (work_dir / "adjudication.json")
    bundle = args.bundle_output or (work_dir / "bundle.json")
    evidence = args.output or (work_dir / "evidence.md")
    card_tags = args.card_tag_output or (work_dir / "card-tags.json")
    bundle_tmp = bundle.with_suffix(bundle.suffix + ".tmp")
    evidence_tmp = evidence.with_suffix(evidence.suffix + ".tmp")
    card_tags_tmp = card_tags.with_suffix(card_tags.suffix + ".tmp")

    remove_if_present(
        bundle, evidence, card_tags, bundle_tmp, evidence_tmp, card_tags_tmp,
    )

    retrieve_command = [
        args.python, str(SCRIPTS / "retrieve.py"), "full",
        "--diagnosis-result", str(diagnosis_result),
        "--adjudication-result", str(adjudication_result),
        "--output", str(bundle_tmp),
    ]
    if args.genes:
        retrieve_command.extend(["--genes", *args.genes])
    if args.corpus:
        retrieve_command.extend(["--corpus", str(args.corpus)])
    if args.index:
        retrieve_command.extend(["--index", str(args.index)])

    run_command(retrieve_command, "step 4: retrieve full evidence bundle")
    require_file(bundle_tmp, "bundle.json")
    bundle_tmp.replace(bundle)

    render_command = [
        args.python, str(SCRIPTS / "render.py"),
        "--bundle", str(bundle),
        "--output", str(evidence_tmp),
        "--card-tag-output", str(card_tags_tmp),
    ]
    if args.token_budget is not None:
        render_command.extend(["--token-budget", str(args.token_budget)])

    run_command(render_command, "step 5: render evidence")
    require_file(evidence_tmp, "evidence.md")
    require_file(card_tags_tmp, "card-tags.json")
    evidence_tmp.replace(evidence)
    card_tags_tmp.replace(card_tags)

    # Surface only the model-readable evidence path. The private card-tag
    # deconvolution map is intentionally not named in command output.
    print(f"[run_case] output: {evidence}", file=sys.stderr)


def main():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--work-dir", type=Path, help="working directory (created if absent)")
    common.add_argument("--python", default=sys.executable, help="Python interpreter to use for children")

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)

    diag = sub.add_parser("diagnosis", parents=[common], help="run Step 2 diagnosis retrieval")
    diag.add_argument("--case-input", type=Path, help="override path to case-input.json")
    diag.add_argument("--output", type=Path, help="override path to diagnostic_evidence.md")
    diag.add_argument("--genes", nargs="+", help="override genes")
    diag.add_argument("--provisional-disease", help="override provisional disease wording")
    diag.add_argument("--case-major-category", help="override case major category")
    diag.add_argument("--case-facts", type=Path, help="override case-facts file")
    diag.add_argument("--corpus", type=Path, help="override corpus path")
    diag.add_argument("--index", type=Path, help="override index path")

    full_parser = sub.add_parser("full", parents=[common], help="run Steps 4 and 5 full retrieval and render")
    full_parser.add_argument(
        "--diagnosis-result", type=Path,
        help="override path to diagnostic_evidence.md",
    )
    full_parser.add_argument("--adjudication-result", type=Path, help="override path to adjudication.json")
    full_parser.add_argument("--bundle-output", type=Path, help="override path to bundle.json")
    full_parser.add_argument("--output", type=Path, help="override path to evidence.md")
    full_parser.add_argument("--card-tag-output", type=Path, help="override path to card-tags.json")
    full_parser.add_argument("--genes", nargs="+", help="override genes for full retrieval")
    full_parser.add_argument("--corpus", type=Path, help="override corpus path")
    full_parser.add_argument("--index", type=Path, help="override index path")
    full_parser.add_argument("--token-budget", type=int, help="forward token budget to renderer")

    args = parser.parse_args()

    try:
        if args.command == "diagnosis":
            diagnosis(args)
        else:
            full(args)
    except (OSError, ValueError) as exc:
        print(f"[run_case] failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()