"""Resolve the deliberately small workflow input-binding vocabulary.

Bindings are data lookups only.  They never evaluate expressions or import code.
"""
from __future__ import annotations

from typing import Any

from workflows.proforma_v1 import layout


def _dig(value: Any, path: str) -> Any:
    cur = value
    for part in path.split(".") if path else []:
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def resolve_reference(ref: str, context) -> Any:
    if ref == "run.case_text":
        path = context.work / "case.md"
        if not path.is_file():
            # Current run layout keeps the immutable input beneath input/.
            path = context.work / "input" / "case.md"
        return path.read_text(encoding="utf-8") if path.is_file() else None
    if ref == "assets.ngs_panel_scope":
        path = layout.setup(context.work, "ngs-panel-scope.md")
        return path.read_text(encoding="utf-8") if path.is_file() else None
    if ref.startswith("artifacts."):
        return context.get(ref.split(".", 1)[1])
    if ref.startswith("settings."):
        return _dig(context.get("settings", {}) or {}, ref.split(".", 1)[1])
    if ref.startswith("feedback."):
        values = context.get("feedback_values", {}) or {}
        return values.get(ref)
    if ref == "owner.cards":
        return context.get("owner_cards")
    return None


def resolve_inputs(step, context) -> dict[str, Any]:
    values = {}
    for name, spec in (step.inputs or {}).items():
        ref = spec.get("from")
        value = resolve_reference(ref, context)
        if value is None and not spec.get("optional", False):
            raise RuntimeError(f"required workflow input {name!r} ({ref}) is unavailable for {step.id!r}")
        values[name] = value
    return values
