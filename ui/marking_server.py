"""Validation-marking extension for the workflow-aware NEL browser server.

The module layers optional validation marking on top of :mod:`ui.workflow_server`.
It keeps marking separate from clinical execution, exposes one explicit POST action,
and injects a small browser extension without duplicating the main UI page.
"""
from __future__ import annotations

import json
import sys
import threading
from pathlib import Path
from typing import Any

from ui import workflow_server as workflow

batch = workflow.batch
base = workflow.base

MARKING_CONTROLS_ASSET = "marking-controls.js"
MARKING_CONTROLS_SCRIPT = f'<script src="/assets/{MARKING_CONTROLS_ASSET}"></script>'


def _json_file(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    return value if isinstance(value, dict) else None


def _functional_definitions() -> dict[str, str]:
    try:
        from validation.scripts.score_functional_dublin import load_spec

        return dict(load_spec().functions)
    except Exception:
        return {}


def marking(run_ref: str) -> dict[str, Any]:
    """Return marking state plus already-written renderable artifacts."""
    kind = batch._top_kind(run_ref)
    if kind in {"legacy", "invalid"}:
        return {
            "available": False,
            "applicable": False,
            "status": "unavailable",
            "kind": kind,
            "text": "",
        }

    if kind == "batch":
        doc = batch._nel_json("batch", "status", "--run-id", run_ref, "--json")
        if not isinstance(doc, dict):
            doc = {}
        state = dict(doc.get("marking") or {})
        location = batch._batch_location(run_ref).path
        markdown = batch._safe_read(location / "batch-marking.md")
        payload = _json_file(location / "batch-marking.json")
        functional = payload.get("functional") if isinstance(payload, dict) else None
        return {
            "available": bool(state.get("applicable")),
            "applicable": bool(state.get("applicable")),
            "status": state.get("status") or "not_applicable",
            "kind": "batch",
            "suite": doc.get("mode"),
            "marked": state.get("marked", 0),
            "total": state.get("total", 0),
            "text": markdown.get("text", "") if markdown.get("exists") else "",
            "payload": payload,
            "functional": functional,
            "functional_definitions": (
                (functional or {}).get("function_definitions")
                if isinstance(functional, dict)
                else None
            ) or (_functional_definitions() if doc.get("mode") == "nel-validate-dublin" else {}),
            "artifacts": state.get("artifacts") or {},
        }

    doc = batch._nel_json("status", "--run-id", run_ref, "--json")
    if not isinstance(doc, dict):
        doc = {}
    state = dict(doc.get("marking") or {})
    location = batch._run_location(run_ref).path
    markdown = batch._safe_read(location / "marking.md")
    payload = _json_file(location / "marking.json")
    functional = _json_file(location / "functional.json") if state.get("status") == "complete" else None
    return {
        "available": bool(state.get("applicable")),
        "applicable": bool(state.get("applicable")),
        "status": state.get("status") or "not_applicable",
        "kind": "batch-child" if kind == "batch-child" else "run",
        "suite": state.get("suite") or doc.get("mode"),
        "case": state.get("case"),
        "text": markdown.get("text", "") if markdown.get("exists") else "",
        "payload": payload,
        "functional": functional,
        "functional_definitions": _functional_definitions() if functional else {},
        "error": state.get("error"),
        "artifacts": state.get("artifacts") or {},
    }


def _mark_execution_target(run_ref: str) -> tuple[str, str]:
    """Return registry owner and pipeline for a single run, child, or batch."""
    kind = batch._top_kind(run_ref)
    if kind in {"legacy", "invalid"}:
        raise base.UIError("marking is unavailable for legacy or invalid run folders", 409)
    if kind == "batch":
        location = batch._batch_location(run_ref)
        return location.batch_id, str(location.manifest.get("pipeline") or "")
    location = batch._run_location(run_ref)
    owner = location.batch_id or location.run_id
    return str(owner), str(location.manifest.get("pipeline") or "")


def action_mark(payload: dict[str, Any]) -> dict[str, Any]:
    run_ref = str(payload.get("run_id") or "").strip()
    if not run_ref:
        raise base.UIError("marking requires a run identifier")
    owner, pipeline = _mark_execution_target(run_ref)
    current = marking(run_ref)
    if not current.get("applicable"):
        raise base.UIError("marking is available only for completed validation runs", 409)
    if current.get("status") == "complete":
        return {"run_id": owner, "phase": "marking", "active": False, "already_complete": True}
    argv = [sys.executable, "-u", str(base.ROOT / "nel.py"), "mark", "--run-id", run_ref]
    return base.REGISTRY.start(
        argv,
        run_id=owner,
        phase="marking",
        exclusive=base.is_local_pipeline_safe(pipeline) if pipeline else True,
    )


# workflow_server owns setup construction. Thread-local argv injection lets this top
# layer add the one frozen policy flag without copying that setup implementation.
_SETUP_CONTEXT = threading.local()
_REGISTRY_START = base.REGISTRY.start
_WORKFLOW_ACTION_SETUP = batch.action_setup


def _registry_start_with_marking(argv: list[str], *args: Any, **kwargs: Any) -> dict[str, Any]:
    values = list(argv)
    if getattr(_SETUP_CONTEXT, "mark_validation", False) and "--mark-validation" not in values:
        values.append("--mark-validation")
    return _REGISTRY_START(values, *args, **kwargs)


def _action_setup_with_marking(payload: dict[str, Any]) -> dict[str, Any]:
    enabled = bool(payload.get("mark_validation"))
    mode = str(payload.get("mode") or "").strip()
    try:
        from validation.scripts.bundled_cases import is_validation_mode
        validation_mode = bool(is_validation_mode(mode))
    except Exception:
        validation_mode = mode == "nel-validate" or mode.startswith("nel-validate-")
    if enabled and not validation_mode:
        raise base.UIError("automatic marking can be enabled only for a validation suite")
    _SETUP_CONTEXT.mark_validation = enabled
    try:
        return _WORKFLOW_ACTION_SETUP(payload)
    finally:
        _SETUP_CONTEXT.mark_validation = False


base.REGISTRY.start = _registry_start_with_marking
batch.action_setup = _action_setup_with_marking

_WORKFLOW_HANDLE = batch.Handler._handle


def _handle_with_marking(self, path: str, method: str) -> Any:
    if method == "GET" and path == "/api/marking":
        return marking(self._param("run"))
    if method == "POST" and path == "/api/mark":
        return action_mark(self._body())
    return _WORKFLOW_HANDLE(self, path, method)


batch.Handler._handle = _handle_with_marking


def _patched_page() -> tuple[Path, Path]:
    source = batch.PAGE
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise base.UIError(f"could not read UI page: {exc}", 500) from exc
    if MARKING_CONTROLS_SCRIPT not in text:
        text = text.replace("</body>", f"{MARKING_CONTROLS_SCRIPT}\n</body>", 1)
    target = base.STATE_DIR / "marking-index.html"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return source, target


def serve(port: int = 8765, open_browser: bool = True) -> int:
    source, patched = _patched_page()
    batch.PAGE = patched
    try:
        return int(workflow.serve(port=port, open_browser=open_browser))
    finally:
        batch.PAGE = source
        try:
            patched.unlink()
        except OSError:
            pass
