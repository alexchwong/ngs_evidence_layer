"""Canonical semantic-dissent ledger, shared by executors and audit overlays.

Before this module existed the ledger lived entirely inside ``step.py`` as
private helpers, so anything outside that file — notably the
``default_reviewed_v2`` audit overlay — could only write findings into an
intermediate artifact that no human-facing surface ever read.  A finding that
is recorded but invisible is not a safety guard, so the ledger itself now lives
here and ``step.py`` delegates to it.

This module owns storage only.  Rendering ``dissent.md`` remains in ``step.py``
because that renderer carries stage-specific presentation heuristics; it
registers itself here via :func:`set_renderer` so any writer can refresh the
human-facing surface without importing the executor.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import yaml

from workflows.proforma_v1 import layout

SCHEMA_VERSION = 2
STATUSES = ("open", "resolved", "retained_with_dissent")

_RENDERER: Callable[[Path], Any] | None = None


def set_renderer(fn: Callable[[Path], Any] | None) -> None:
    """Register the human-facing ``dissent.md`` writer.

    ``step.py`` calls this at import time.  Kept as a hook rather than a direct
    import so the ledger has no dependency on the executor.
    """
    global _RENDERER
    _RENDERER = fn


def _refresh(work: Path) -> None:
    if _RENDERER is not None:
        try:
            _RENDERER(Path(work))
        except Exception:
            # Ledger persistence must never be lost because presentation failed.
            pass


def path(work: Path) -> Path:
    return layout.logs(Path(work)) / "semantic_dissent.yaml"


def _write(target: Path, text: str) -> Path:
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(target)
    return target


def _dump(work: Path, doc: dict) -> None:
    _write(path(work), yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=110))


def _strings(value: Any) -> list[str]:
    rows = value if isinstance(value, list) else [value]
    return [str(x).strip() for x in rows if str(x or "").strip()]


def doc(work: Path) -> dict:
    """Load the ledger, migrating the legacy flat ``items`` schema on the way."""
    target = path(work)
    if target.is_file():
        try:
            loaded = yaml.safe_load(target.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError, TypeError):
            loaded = {}
        if isinstance(loaded, dict) and isinstance(loaded.get("issues"), list):
            loaded.setdefault("schema_version", SCHEMA_VERSION)
            return loaded
        if isinstance(loaded, dict) and isinstance(loaded.get("items"), list):
            issues = []
            for index, row in enumerate(loaded.get("items") or [], 1):
                reviewed = str(row.get("reviewed_text") or "").strip()
                reasons = _strings(row.get("dissent_reason"))
                actions = _strings(row.get("action_recommended"))
                if not reviewed or not reasons or not actions:
                    continue
                did = str(row.get("id") or f"D{index:03d}")
                issues.append({
                    "id": did,
                    "issue_key": f"legacy:{did}",
                    "reviewed_text": reviewed,
                    "status": "open",
                    "history": [{
                        "stage": "legacy semantic dissent",
                        "event": "raised",
                        "reason": reasons,
                        "resolution_recommendation": actions,
                    }],
                })
            migrated = {"schema_version": SCHEMA_VERSION, "issues": issues}
            _dump(work, migrated)
            return migrated
    return {"schema_version": SCHEMA_VERSION, "issues": []}


def issue(work: Path, issue_key: str) -> dict | None:
    key = str(issue_key or "").strip()
    if not key:
        return None
    for row in doc(work).get("issues") or []:
        if row.get("issue_key") == key:
            return row
    return None


def raise_issue(work: Path, *, issue_key, stage, reviewed_text, dissent_reason, action_recommended) -> str | None:
    """Raise or revisit one semantic dissent issue.

    ``issue_key`` is stable across retries and self handoffs and is never
    rendered.  Repeated raises append history only when the stage, reason or
    recommendation differs, so replay stays idempotent.
    """
    key = str(issue_key or "").strip()
    stage = str(stage or "").strip()
    reviewed = str(reviewed_text or "").strip()
    reasons = _strings(dissent_reason)
    actions = _strings(action_recommended)
    if not key or not stage or not reviewed or not reasons or not actions:
        return None
    document = doc(work)
    issues = document.setdefault("issues", [])
    row = next((r for r in issues if r.get("issue_key") == key), None)
    if row is None:
        did = f"D{len(issues) + 1:03d}"
        row = {"id": did, "issue_key": key, "reviewed_text": reviewed, "status": "open", "history": []}
        issues.append(row)
    else:
        did = row.get("id")
        if not row.get("reviewed_text"):
            row["reviewed_text"] = reviewed
        # A recurring concern reopens the issue unless it was deliberately
        # retained with dissent.
        if row.get("status") == "resolved":
            row["status"] = "open"
    event = {"stage": stage, "event": "raised", "reason": reasons, "resolution_recommendation": actions}
    if event not in row.setdefault("history", []):
        row["history"].append(event)
    _dump(work, document)
    _refresh(work)
    return did


def address(work: Path, *, issue_key, stage, action, outcome=None, status=None) -> str | None:
    """Append an action/outcome to an existing semantic dissent issue."""
    key = str(issue_key or "").strip()
    stage = str(stage or "").strip()
    actions = _strings(action)
    outcomes = _strings(outcome)
    if not key or not stage or not actions:
        return None
    document = doc(work)
    issues = document.setdefault("issues", [])
    row = next((r for r in issues if r.get("issue_key") == key), None)
    if row is None:
        return None
    event = {"stage": stage, "event": "addressed", "action": actions}
    if outcomes:
        event["outcome"] = outcomes
    if event not in row.setdefault("history", []):
        row["history"].append(event)
    if status:
        if status not in STATUSES:
            raise ValueError(f"unsupported dissent status: {status}")
        row["status"] = status
    _dump(work, document)
    _refresh(work)
    return row.get("id")


def keys(work: Path, prefix: str, *, statuses=("open",)) -> list[str]:
    wanted = set(statuses or [])
    return [
        str(row.get("issue_key"))
        for row in doc(work).get("issues") or []
        if str(row.get("issue_key") or "").startswith(prefix) and (not wanted or row.get("status") in wanted)
    ]
