"""Presentation-only summarization of the canonical semantic-dissent ledger.

This module may read the ledger and write ``dissent.md``. It never mutates the
ledger and never participates in clinical decisions, evidence review, retries,
or report generation.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from workflows.proforma_v1.engine import dissent


def _strings(value: Any) -> list[str]:
    rows = value if isinstance(value, list) else [value]
    return [str(x).strip() for x in rows if str(x or "").strip()]


def build_packet(work: Path) -> list[dict[str, Any]]:
    """Project canonical ledger issues into a bounded presentation packet."""
    packet: list[dict[str, Any]] = []
    for issue in dissent.doc(Path(work)).get("issues") or []:
        if not isinstance(issue, dict):
            continue
        issue_id = str(issue.get("id") or "").strip()
        statement = str(issue.get("reviewed_text") or "").strip()
        if not issue_id or not statement:
            continue
        events = []
        for event in issue.get("history") or []:
            if not isinstance(event, dict):
                continue
            row = {
                "stage": str(event.get("stage") or "").strip(),
                "event": str(event.get("event") or "").strip(),
            }
            for key in ("reason", "resolution_recommendation", "action", "outcome"):
                values = _strings(event.get(key))
                if values:
                    row[key] = values
            events.append(row)
        packet.append({
            "issue_id": issue_id,
            "statement": statement,
            "status": str(issue.get("status") or "open").strip() or "open",
            "events": events,
        })
    return packet


def validate_summary(packet: Any, summary: Any) -> dict[str, Any]:
    """Enforce exact source-ID coverage before model prose may replace dissent.md."""
    source = packet if isinstance(packet, list) else []
    expected = [str(row.get("issue_id") or "").strip() for row in source if isinstance(row, dict)]
    expected = [x for x in expected if x]
    if not expected:
        return {"accepted": False, "reason": "no source dissent", "items": []}
    if not isinstance(summary, dict) or not isinstance(summary.get("items"), list):
        return {"accepted": False, "reason": "summary is missing items", "items": []}

    seen: list[str] = []
    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(summary.get("items") or [], 1):
        if not isinstance(item, dict):
            return {"accepted": False, "reason": f"item {index} is not an object", "items": []}
        ids = _strings(item.get("source_issue_ids"))
        if not ids:
            return {"accepted": False, "reason": f"item {index} has no source_issue_ids", "items": []}
        fields = {key: str(item.get(key) or "").strip() for key in ("statement", "concern", "decision_and_basis")}
        if not all(fields.values()):
            return {"accepted": False, "reason": f"item {index} is missing required presentation text", "items": []}
        seen.extend(ids)
        normalized.append({"source_issue_ids": ids, **fields})

    counts = Counter(seen)
    duplicated = sorted(k for k, v in counts.items() if v != 1)
    unknown = sorted(set(seen) - set(expected))
    missing = sorted(set(expected) - set(seen))
    if duplicated:
        return {"accepted": False, "reason": f"source issue IDs not represented exactly once: {', '.join(duplicated)}", "items": []}
    if unknown:
        return {"accepted": False, "reason": f"unknown source issue IDs: {', '.join(unknown)}", "items": []}
    if missing:
        return {"accepted": False, "reason": f"missing source issue IDs: {', '.join(missing)}", "items": []}
    if len(seen) != len(expected):
        return {"accepted": False, "reason": "source issue coverage is not exact", "items": []}
    return {"accepted": True, "reason": "exact source coverage", "items": normalized}


def render_markdown(validation: Any) -> str:
    """Render only a previously validated presentation summary."""
    if not isinstance(validation, dict) or validation.get("accepted") is not True:
        return ""
    items = validation.get("items") or []
    sections = ["# Semantic dissent"]
    for item in items:
        source = ", ".join(item.get("source_issue_ids") or [])
        sections.extend([
            "",
            "## Statement",
            str(item.get("statement") or "").strip(),
            "",
            f"**Concern / Critique:**  \n{str(item.get('concern') or '').strip()}",
            "",
            f"**Decision and Basis:**  \n{str(item.get('decision_and_basis') or '').strip()}",
            "",
            f"*Source dissent: {source}*",
        ])
    return "\n".join(sections).rstrip() + "\n"


def install(work: Path, validation: Any) -> dict[str, Any]:
    """Replace dissent.md only after successful deterministic validation."""
    path = Path(work) / "dissent.md"
    markdown = render_markdown(validation)
    if not markdown:
        return {"installed": False, "reason": str((validation or {}).get("reason") or "summary rejected")}
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(markdown, encoding="utf-8")
    tmp.replace(path)
    return {"installed": True, "path": str(path), "source_issue_count": sum(len(x.get("source_issue_ids") or []) for x in validation.get("items") or [])}
