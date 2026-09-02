"""Workflow-definition aware wrapper for the batch NEL browser server.

The existing :mod:`ui.batch_server` remains the batch/provider implementation.
This wrapper adds discovery and selection of declarative proforma-v1 workflow
YAMLs without duplicating workflow execution logic in the UI.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from ui import batch_server as batch

base = batch.base
_BATCH_BOOTSTRAP = batch.bootstrap
WORKFLOW_DIR = base.ROOT / "workflows" / "proforma_v1" / "workflow"
DEFAULT_WORKFLOW = "default"


def workflow_definitions() -> list[dict[str, str]]:
    rows = [
        {"id": path.stem, "label": path.stem}
        for path in sorted(WORKFLOW_DIR.glob("*.yaml"))
        if path.is_file() and base.RUN_ID_RE.fullmatch(path.stem)
    ]
    if not rows:
        raise base.UIError(f"no proforma-v1 workflow YAML files found in {WORKFLOW_DIR}", 500)
    return rows


def _workflow_name(payload: dict[str, Any]) -> str:
    name = str(payload.get("workflow") or DEFAULT_WORKFLOW).strip()
    available = {row["id"] for row in workflow_definitions()}
    if name not in available:
        raise base.UIError(
            f"unknown workflow {name!r}; choose one of: {', '.join(sorted(available))}",
            400,
        )
    return name


def bootstrap() -> dict[str, Any]:
    doc = _BATCH_BOOTSTRAP()
    doc["workflows"] = workflow_definitions()
    doc["default_workflow"] = DEFAULT_WORKFLOW
    return doc


def _single_setup(payload: dict[str, Any], workflow: str) -> dict[str, Any]:
    pipeline = str(payload.get("pipeline") or "").strip()
    batch._validate_pipeline(pipeline)
    mode = str(payload.get("mode") or "").strip()
    if mode not in set(base.modes()):
        raise base.UIError(f"unsupported mode {mode!r}; choose one of: {', '.join(base.modes())}")

    label = mode
    args: list[str] = ["--workflow", workflow]
    case_text = ""
    if mode == "ngs-report":
        case_text = str(payload.get("case_text") or "")
        if not case_text.strip():
            raise base.UIError("paste the clinical case before preparing a run")
        label = "case"
    elif mode == "nel-demo":
        example = payload.get("example")
        if example in (None, ""):
            raise base.UIError("choose a demo example before preparing a run")
        args += ["--example", str(int(example))]
        label = f"demo-{int(example)}"
    else:
        case_id = str(payload.get("case_id") or "").strip()
        if not case_id:
            raise base.UIError("choose a validation case before preparing a run")
        args += ["--case-id", case_id]
        label = f"{mode.removeprefix('nel-')}-{case_id}"

    cul = str(payload.get("cul") or "").strip()
    if cul:
        args += ["--cul", cul]

    supplied = str(payload.get("run_id") or "").strip()
    run_id = base.check_run_id(supplied) if supplied else base.generated_run_id(label)
    if base.run_dir(run_id).exists():
        raise base.UIError(f"a run named {run_id} already exists; choose another identifier", 409)

    cleanup: list[Path] = []
    if mode == "ngs-report":
        path = base.case_path(run_id)
        text = case_text if case_text.endswith("\n") else case_text + "\n"
        path.write_text(text, encoding="utf-8")
        args += ["--case", str(path)]
        cleanup.append(path)

    argv = [
        sys.executable,
        "-u",
        str(base.ROOT / "nel.py"),
        "setup",
        "--mode",
        mode,
        "--pipeline",
        pipeline,
        "--run-id",
        run_id,
        *args,
    ]
    try:
        return base.REGISTRY.start(
            argv,
            run_id=run_id,
            phase="setup",
            exclusive=base.is_local_pipeline(pipeline),
            cleanup=cleanup,
        )
    except base.UIError:
        for path in cleanup:
            try:
                path.unlink()
            except OSError:
                pass
        raise


def action_setup(payload: dict[str, Any]) -> dict[str, Any]:
    workflow = _workflow_name(payload)
    if not bool(payload.get("batch_mode")):
        return _single_setup(payload, workflow)

    mode = str(payload.get("mode") or "").strip()
    pipeline = str(payload.get("pipeline") or "").strip()
    batch._validate_pipeline(pipeline)
    cul = str(payload.get("cul") or "").strip()
    args = [
        "batch",
        "setup",
        "--workflow",
        workflow,
        "--mode",
        mode,
        "--pipeline",
        pipeline,
    ]
    cleanup: list[Path] = []

    if cul:
        args += ["--cul", cul]
    if mode == "ngs-report":
        case_text_value = str(payload.get("case_text") or "")
        try:
            parsed = batch.run_layout.parse_case_markdown(case_text_value)
        except batch.run_layout.LayoutError as exc:
            raise base.UIError(str(exc)) from exc
        batch_id = batch._new_batch_id(payload, f"cases-{len(parsed)}")
        source = base.case_path(batch_id)
        source.write_text(
            case_text_value if case_text_value.endswith("\n") else case_text_value + "\n",
            encoding="utf-8",
        )
        cleanup.append(source)
        args += ["--case", str(source), "--run-id", batch_id]
    else:
        suites = {row["mode"]: set(row.get("cases") or []) for row in batch._bundled_suites()}
        if mode not in suites:
            raise base.UIError(f"unsupported bundled batch series {mode!r}")
        raw_ids = payload.get("case_ids") or []
        if not isinstance(raw_ids, list):
            raise base.UIError("bundled case_ids must be a list")
        case_ids = [str(value).strip() for value in raw_ids if str(value).strip()]
        if not case_ids:
            raise base.UIError("select at least one case from this bundled series")
        missing = [case_id for case_id in case_ids if case_id not in suites[mode]]
        if missing:
            raise base.UIError(
                f"case(s) not in {mode}: {', '.join(missing)}; select cases from one series only"
            )
        try:
            joined = ",".join(batch.run_layout.parse_case_ids(",".join(case_ids)))
        except batch.run_layout.LayoutError as exc:
            raise base.UIError(str(exc)) from exc
        batch_id = batch._new_batch_id(payload, f"{mode.removeprefix('nel-')}-{len(case_ids)}")
        args += ["--case-ids", joined, "--run-id", batch_id]

    argv = [sys.executable, "-u", str(base.ROOT / "nel.py"), *args]
    try:
        return base.REGISTRY.start(
            argv,
            run_id=batch_id,
            phase="setup",
            exclusive=base.is_local_pipeline(pipeline),
            cleanup=cleanup,
        )
    except base.UIError:
        for path in cleanup:
            try:
                path.unlink()
            except OSError:
                pass
        raise


# Handler methods in batch_server resolve these names in the batch_server module.
batch.bootstrap = bootstrap
batch.action_setup = action_setup


def serve(port: int = 8765, open_browser: bool = True) -> int:
    return int(batch.serve(port=port, open_browser=open_browser))
