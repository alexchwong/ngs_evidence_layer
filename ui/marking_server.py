"""Automatic-marking extension for the workflow-aware NEL browser server.

This module deliberately layers on top of :mod:`ui.workflow_server` rather than
copying its provider/workflow/model-activity routing.  The only additional HTTP
surface is ``GET /api/marking``; all mutating actions still flow through root
``nel.py``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ui import workflow_server as workflow

batch = workflow.batch
base = workflow.base


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
    """Return automatic-marking state and current renderable artifacts.

    The endpoint never retrieves evaluator criteria itself.  Status comes from
    root ``nel.py`` and the endpoint only reads artifacts that already exist in
    the run directory, preserving the post-report evaluator isolation boundary.
    """
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
        functional = None
        if isinstance(payload, dict):
            functional = payload.get("functional")
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
            ) or _functional_definitions() if doc.get("mode") == "nel-validate-dublin" else {},
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


_WORKFLOW_HANDLE = batch.Handler._handle


def _handle_with_marking(self, path: str, method: str) -> Any:
    if method == "GET" and path == "/api/marking":
        return marking(self._param("run"))
    return _WORKFLOW_HANDLE(self, path, method)


batch.Handler._handle = _handle_with_marking


def serve(port: int = 8765, open_browser: bool = True) -> int:
    return int(workflow.serve(port=port, open_browser=open_browser))
