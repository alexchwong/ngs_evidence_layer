#!/usr/bin/env python3
"""Create/reuse one work directory, bind it to a workflow, and prepare shared setup assets."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import vocab  # noqa: E402
from scripts.workflow_registry import (  # noqa: E402
    import_workflow_module,
    load_registry,
    load_workflow_metadata,
    normalise_selector,
    write_workflow_state,
)
from workflows.common import demo_paths, resolve_work_dir, write_case_major_categories  # noqa: E402


def setup_workflow(
    *,
    workflow: str | None,
    mode: str,
    work_dir: Path | None = None,
    project: bool = False,
    example: int | None = None,
    case_id: str | None = None,
) -> tuple[Path, Path | None, Path | None]:
    registry = load_registry()
    workflow_id = normalise_selector(workflow, registry)
    metadata = load_workflow_metadata(workflow_id, registry)
    supported = metadata.get("supported_modes") or []
    if mode not in supported:
        raise ValueError(
            f"workflow {workflow_id!r} does not support mode {mode!r}. Supported modes: "
            + ", ".join(supported)
        )
    if mode == "nel-demo" and example is None:
        raise ValueError("nel-demo requires --example")
    if mode != "nel-demo" and example is not None:
        raise ValueError("--example is valid only for nel-demo")
    if mode in {"nel-validate", "nel-validate-function"} and not case_id:
        raise ValueError(f"{mode} requires --case-id")
    if mode not in {"nel-validate", "nel-validate-function"} and case_id is not None:
        raise ValueError("--case-id is valid only for validation modes")

    work = resolve_work_dir(work_dir, project=project)
    write_workflow_state(work, workflow_id, mode)

    # Common procedural asset. evidence-to-report intentionally reuses existing
    # Step-5 outputs and does not create irrelevant Step-1 state.
    if mode != "evidence-to-report":
        write_case_major_categories(work / "case-major-categories.json", vocab.CASE_MAJOR_CATEGORIES)

    demo_case = demo_expected = None
    if mode == "nel-demo":
        demo_case, demo_expected = demo_paths(example)

    # Optional workflow-owned setup hook for genuinely workflow-specific assets.
    try:
        runtime = import_workflow_module(workflow_id, "runtime")
    except ModuleNotFoundError as exc:
        package = metadata["python_package"]
        if exc.name != f"{package}.runtime":
            raise
    else:
        hook = getattr(runtime, "setup_assets", None)
        if hook is not None:
            hook(work, mode=mode, case_id=case_id)

    return work, demo_case, demo_expected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workflow", help="workflow ID or alias; default is registry default")
    parser.add_argument(
        "--mode",
        required=True,
        choices=(
            "evidence-block",
            "evidence-block-manual",
            "ngs-report",
            "evidence-to-report",
            "nel-demo",
            "nel-validate",
            "nel-validate-function",
        ),
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--work-dir", type=Path)
    group.add_argument("--project", action="store_true")
    parser.add_argument("--example", type=int)
    parser.add_argument("--case-id")
    args = parser.parse_args()
    try:
        work, demo_case, demo_expected = setup_workflow(
            workflow=args.workflow,
            mode=args.mode,
            work_dir=args.work_dir,
            project=args.project,
            example=args.example,
            case_id=args.case_id,
        )
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"workflow setup failed: {exc}\n")
    print(work)
    if demo_case is not None:
        print(demo_case.relative_to(REPO_ROOT))
        print(demo_expected.relative_to(REPO_ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
