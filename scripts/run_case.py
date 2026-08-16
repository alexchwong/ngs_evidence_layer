#!/usr/bin/env python3
"""Run one deterministic case-pipeline stage for the workflow bound to a work directory.

Public runtime CLI:
  run_case.py diagnosis --work-dir <directory>
  run_case.py downstream --work-dir <directory>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.workflow_registry import import_workflow_module, workflow_for_work_dir  # noqa: E402


def run_stage(stage: str, work_dir: Path, python: str) -> None:
    work = work_dir.resolve()
    workflow_id, _metadata = workflow_for_work_dir(work)
    pipeline = import_workflow_module(workflow_id, "case_pipeline")
    implementation = getattr(pipeline, stage, None)
    if implementation is None:
        raise ValueError(f"workflow {workflow_id!r} does not implement case stage {stage!r}")
    implementation(work, python)


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("stage", choices=("diagnosis", "downstream"))
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--python", default=sys.executable)
    args = parser.parse_args()
    try:
        run_stage(args.stage, args.work_dir, args.python)
    except (OSError, ValueError, RuntimeError) as exc:
        parser.exit(1, f"[run_case] failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
