#!/usr/bin/env python3
"""Dispatch workflow-owned deterministic runtime operations using work-dir state."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.workflow_registry import import_workflow_module, workflow_for_work_dir  # noqa: E402


def _runtime(work_dir: Path):
    workflow_id, _metadata = workflow_for_work_dir(work_dir)
    try:
        return workflow_id, import_workflow_module(workflow_id, "runtime")
    except ModuleNotFoundError as exc:
        raise ValueError(
            f"workflow {workflow_id!r} does not define deterministic runtime operations"
        ) from exc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("cmc", "remainder-rules", "validate-remainder", "assemble", "render"))
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    work = args.work_dir.resolve()
    try:
        workflow_id, runtime = _runtime(work)
        if args.command == "cmc":
            refined = runtime.validate_diagnosis_draft(
                work / "report-draft-dx.yaml",
                work / "diagnostic_evidence.md",
                work / "reporting-rules-dx.md",
            )
            print(refined)
        elif args.command == "remainder-rules":
            initial, refined, changed = runtime.diagnosis_first_branch(
                work / "case-input.json", work / "report-draft-dx.yaml"
            )
            sections = set(range(0, 6)) if changed else {2, 3, 4, 5}
            path = runtime.write_rule_slice(
                runtime.DEFAULT_RULES,
                work / "reporting-rules-remainder.md",
                sections,
            )
            print(path)
            print(f"INITIAL_CMC={initial}")
            print(f"REFINED_CMC={refined}")
            print(f"CMC_CHANGED={'yes' if changed else 'no'}")
        elif args.command == "validate-remainder":
            runtime.validate_remainder_draft(
                work / "report-draft-remainder.yaml",
                work / "downstream_evidence.md",
                work / "reporting-rules-remainder.md",
            )
            print(work / "report-draft-remainder.yaml")
        elif args.command == "assemble":
            path, changed, refined = runtime.assemble_report_draft(
                work / "case-input.json",
                work / "report-draft-dx.yaml",
                work / "report-draft-remainder.yaml",
                work / "report-draft.yaml",
                work / "diagnostic_evidence.md",
                work / "downstream_evidence.md",
                work / "reporting-rules-dx.md",
                work / "reporting-rules-remainder.md",
            )
            print(path)
            print(path.with_name("report-summary.yaml"))
            print(f"REFINED_CMC={refined}")
            print(f"CMC_CHANGED={'yes' if changed else 'no'}")
        else:
            path = runtime.render_report_summary(
                work / "report-summary.yaml",
                work / "report-draft.yaml",
                work / "evidence.md",
                work / "card-tags.json",
                work / "report-final.md",
            )
            print(path)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"workflow runtime failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
