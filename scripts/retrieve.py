#!/usr/bin/env python3
"""Dispatch deterministic evidence retrieval to the workflow bound to a work directory."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.workflow_registry import import_workflow_entrypoint, workflow_for_work_dir  # noqa: E402


def run_stage(stage: str, work_dir: Path) -> Path:
    work = work_dir.resolve()
    workflow_id, _metadata = workflow_for_work_dir(work)
    retrieval = import_workflow_entrypoint(workflow_id, "retrieval")
    implementation = getattr(retrieval, stage, None)
    if implementation is None:
        raise ValueError(f"workflow {workflow_id!r} does not implement retrieval stage {stage!r}")
    return implementation(work)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("diagnosis", "downstream"))
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = run_stage(args.stage, args.work_dir)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"retrieval failed: {exc}\n")
    print(f"wrote {output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
