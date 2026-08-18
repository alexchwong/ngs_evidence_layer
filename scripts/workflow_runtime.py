#!/usr/bin/env python3
"""Dispatch a deterministic runtime command to the workflow bound to a work directory."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.workflow_registry import import_workflow_entrypoint, workflow_for_work_dir  # noqa: E402


def run_command(command: str, work_dir: Path) -> list[str]:
    work = work_dir.resolve()
    workflow_id, _metadata = workflow_for_work_dir(work)
    try:
        runtime = import_workflow_entrypoint(workflow_id, "runtime")
    except ModuleNotFoundError as exc:
        raise ValueError(f"workflow {workflow_id!r} does not define deterministic runtime operations") from exc
    implementation = getattr(runtime, "run", None)
    if implementation is None:
        raise ValueError(f"workflow {workflow_id!r} runtime has no generic run(command, work_dir) entrypoint")
    result = implementation(command, work)
    if result is None:
        return []
    if isinstance(result, str):
        return [result]
    return [str(item) for item in result]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command")
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        lines = run_command(args.command, args.work_dir)
        for line in lines:
            print(line)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"workflow runtime failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
