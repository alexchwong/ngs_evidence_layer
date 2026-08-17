#!/usr/bin/env python3
"""Dispatch report-draft audit validation to the workflow bound to the draft work directory."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.workflow_registry import import_workflow_entrypoint, workflow_for_work_dir  # noqa: E402


def validate_for_workflow(draft: Path, evidence: Path, rules: Path, *, allow_no_evidence_tags=False):
    work_dir = draft.resolve().parent
    workflow_id, _metadata = workflow_for_work_dir(work_dir)
    policy = import_workflow_entrypoint(workflow_id, "audit_policy")
    return policy.validate_draft(
        draft.read_text(encoding="utf-8"),
        evidence.read_text(encoding="utf-8"),
        rules.read_text(encoding="utf-8"),
        allow_no_evidence_tags=allow_no_evidence_tags,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--draft", type=Path, required=True)
    validate.add_argument("--evidence", type=Path, required=True)
    validate.add_argument(
        "--rules", type=Path, default=REPO_ROOT / "rules" / "agreed_reporting_rules.md"
    )
    validate.add_argument("--allow-no-evidence-tags", action="store_true")
    args = parser.parse_args()
    try:
        validate_for_workflow(
            args.draft,
            args.evidence,
            args.rules,
            allow_no_evidence_tags=args.allow_no_evidence_tags,
        )
    except (OSError, ValueError, KeyError) as exc:
        print(f"REPORT AUDIT VALIDATE FAILED: {exc}", file=sys.stderr)
        return 1
    print(args.draft)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
