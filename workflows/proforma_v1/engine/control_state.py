"""Persist executor-neutral workflow control state across native-self handoffs."""
from __future__ import annotations

import json
from pathlib import Path

_FILENAME = "workflow-control.json"
_KEYS = ("review_cycles", "feedback_values", "forced_route")


def path(work: Path) -> Path:
    p = Path(work) / "logs" / _FILENAME
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def load(work: Path) -> dict:
    p = path(work)
    if not p.is_file():
        return {}
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"invalid persisted workflow control state {p}: {exc}") from exc
    return doc if isinstance(doc, dict) else {}


def hydrate(context) -> None:
    doc = load(context.work)
    for key in _KEYS:
        if key in doc:
            context.put(key, doc[key])


def save(context) -> None:
    doc = {key: context.get(key) for key in _KEYS if context.get(key) not in (None, {}, "")}
    p = path(context.work)
    p.write_text(json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
