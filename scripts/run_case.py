#!/usr/bin/env python3
"""Thin deterministic wrapper dispatching to isolated workflow case pipelines.

Public CLI is unchanged:
  run_case.py diagnosis --work-dir <directory>
  run_case.py full --work-dir <directory>
  run_case.py prototype-diagnosis --work-dir <directory>
  run_case.py prototype-downstream --work-dir <directory>
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def diagnosis(args):
    from workflows.legacy.case_pipeline import diagnosis as implementation
    return implementation(args)


def full(args):
    from workflows.legacy.case_pipeline import full as implementation
    return implementation(args)


def prototype_diagnosis(args):
    from workflows.prototype.case_pipeline import prototype_diagnosis as implementation
    return implementation(args)


def prototype_downstream(args):
    from workflows.prototype.case_pipeline import prototype_downstream as implementation
    return implementation(args)


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
    diag.add_argument("--blacklist", type=Path, help="override blacklist policy path")

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
    full_parser.add_argument("--blacklist", type=Path, help="override blacklist policy path")
    full_parser.add_argument("--token-budget", type=int, help="forward token budget to renderer")

    prototype_diag = sub.add_parser(
        "prototype-diagnosis", parents=[common], help="run prototype Step 2"
    )
    prototype_diag.add_argument("--case-input", type=Path, help="override path to case-input.json")
    prototype_diag.add_argument("--bundle-output", type=Path, help="override private diagnostic JSON boundary")
    prototype_diag.add_argument("--output", type=Path, help="override path to diagnostic_evidence.md")
    prototype_diag.add_argument("--corpus", type=Path, help="override corpus path")
    prototype_diag.add_argument("--index", type=Path, help="override index path")
    prototype_diag.add_argument("--blacklist", type=Path, help="override blacklist policy path")
    prototype_diag.add_argument("--token-budget", type=int, help="forward token budget to renderer")

    prototype_full = sub.add_parser(
        "prototype-downstream", parents=[common], help="run prototype Step 4 retrieval/render"
    )
    prototype_full.add_argument("--diagnosis-result", type=Path, help="override prototype diagnostic JSON boundary")
    prototype_full.add_argument("--diagnosis-draft", type=Path, help="override report-draft-dx.md")
    prototype_full.add_argument("--bundle-output", type=Path, help="override path to bundle.json")
    prototype_full.add_argument("--output", type=Path, help="override path to downstream_evidence.md")
    prototype_full.add_argument("--combined-output", type=Path, help="override path to combined evidence.md")
    prototype_full.add_argument("--card-tag-output", type=Path, help="override path to card-tags.json")
    prototype_full.add_argument("--genes", nargs="+", help="override genes")
    prototype_full.add_argument("--corpus", type=Path, help="override corpus path")
    prototype_full.add_argument("--index", type=Path, help="override index path")
    prototype_full.add_argument("--blacklist", type=Path, help="override blacklist policy path")
    prototype_full.add_argument("--token-budget", type=int, help="forward token budget to renderer")

    args = parser.parse_args()

    try:
        if args.command == "diagnosis":
            diagnosis(args)
        elif args.command == "full":
            full(args)
        elif args.command == "prototype-diagnosis":
            prototype_diagnosis(args)
        else:
            prototype_downstream(args)
    except (OSError, ValueError) as exc:
        print(f"[run_case] failed: {exc}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()