"""Generic evidence assignment, audit and adjudication mechanics."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class EvidenceError(ValueError):
    pass


@dataclass(frozen=True)
class EvidencePolicy:
    name: str
    assignment: dict
    audit: dict
    adjudication: dict


def policies_from_workflow(doc: dict) -> dict[str, EvidencePolicy]:
    out = {}
    for name, row in (doc.get("evidence_policies") or {}).items():
        out[name] = EvidencePolicy(name, dict(row["assignment"]), dict(row["audit"]), dict(row["adjudication"]))
    return out


def owner_envelope(*, owner: str, candidate_card_tags: list[str] | tuple[str, ...], artifact: Any = None, metadata: dict | None = None) -> dict:
    return {
        "owner": owner,
        "candidate_card_tags": list(candidate_card_tags),
        "artifact": artifact,
        "metadata": dict(metadata or {}),
    }


def _path_rows(doc: Any, path: str) -> list[tuple[Any, Any]]:
    """Return ``(row,value)`` pairs with at most one list expansion (``[]``)."""
    if not path:
        return [(doc, doc)]
    if "[]" not in path:
        cur = doc
        for part in path.split("."):
            if not isinstance(cur, dict):
                return []
            cur = cur.get(part)
        return [(doc, cur)]
    prefix, suffix = path.split("[]", 1)
    cur = doc
    for part in prefix.strip(".").split(".") if prefix.strip(".") else []:
        if not isinstance(cur, dict):
            return []
        cur = cur.get(part)
    rows = cur if isinstance(cur, list) else []
    suffix = suffix.lstrip(".")
    out = []
    for row in rows:
        value = row
        if suffix:
            for part in suffix.split("."):
                if not isinstance(value, dict):
                    value = None
                    break
                value = value.get(part)
        out.append((row, value))
    return out


def _condition(row: Any, when: dict | None) -> bool:
    if not when:
        return True
    value = row
    for part in str(when.get("path") or "").split("."):
        if part:
            value = value.get(part) if isinstance(value, dict) else None
    if "equals" in when:
        return value == when["equals"]
    if "in" in when:
        return value in when["in"]
    if "not_in" in when:
        return value not in when["not_in"]
    return bool(value)


def extract_claims(*, owner: str, artifact: Any, declarations: list[dict] | tuple[dict, ...], candidate_card_tags: list[str] | tuple[str, ...], start: int = 1) -> list[dict]:
    claims = []
    sequence = start
    for declaration in declarations or ():
        path = str(declaration.get("path") or "").strip()
        if not path:
            raise EvidenceError("claim declaration requires non-empty path")
        id_from = declaration.get("id_from")
        for row, value in _path_rows(artifact, path):
            if value in (None, "") or not _condition(row, declaration.get("when")):
                continue
            owner_item_id = None
            if id_from:
                id_rows = _path_rows(artifact, str(id_from))
                # For matching list paths, recover the field from the current row.
                suffix = str(id_from).split("[]", 1)[-1].lstrip(".") if "[]" in str(id_from) else str(id_from)
                cur = row
                for part in suffix.split(".") if suffix else []:
                    cur = cur.get(part) if isinstance(cur, dict) else None
                owner_item_id = cur
            claims.append({
                "evidence_id": f"E{sequence:04d}",
                "owner": owner,
                "owner_item_id": owner_item_id,
                "claim": str(value),
                "candidate_card_tags": list(candidate_card_tags),
            })
            sequence += 1
    return claims


def audit_targets(claim: dict, assigned_card_tags: list[str] | tuple[str, ...]) -> list[str]:
    """Positive assignments audit selected cards; zero assignments audit all."""
    selected = list(assigned_card_tags or [])
    candidates = list(claim.get("candidate_card_tags") or claim.get("candidate_cards") or [])
    unknown = sorted(set(selected) - set(candidates))
    if unknown:
        raise EvidenceError(f"assignment introduced card(s) outside candidate envelope: {unknown}")
    return selected if selected else candidates


def compare(*, claim: dict, assigned_card_tags: list[str] | tuple[str, ...], audit_rows: list[dict] | tuple[dict, ...]) -> dict:
    selected = set(assigned_card_tags or [])
    candidates = set(claim.get("candidate_card_tags") or claim.get("candidate_cards") or [])
    if not selected <= candidates:
        raise EvidenceError("assignment contains a card outside the candidate set")
    rows = {str(row.get("card_tag")): row for row in audit_rows or ()}
    if not set(rows) <= candidates:
        raise EvidenceError("audit contains a card outside the candidate set")
    agreed = []
    disputes = []
    for tag, row in rows.items():
        decision = row.get("decision")
        if decision not in {"include", "exclude"}:
            raise EvidenceError(f"invalid audit decision for {tag!r}: {decision!r}")
        if tag in selected and decision == "include":
            agreed.append(tag)
        elif tag in selected and decision == "exclude":
            disputes.append({
                "evidence_id": claim.get("evidence_id"),
                "claim": claim.get("claim"),
                "card_tag": tag,
                "dispute_type": "resolver_include_auditor_exclude",
                "resolver_decision": "include",
                "auditor_decision": "exclude",
                "audit_comments": row.get("comments") or row.get("reason"),
            })
        elif tag not in selected and decision == "include":
            disputes.append({
                "evidence_id": claim.get("evidence_id"),
                "claim": claim.get("claim"),
                "card_tag": tag,
                "dispute_type": "resolver_zero_auditor_include",
                "resolver_decision": "exclude",
                "auditor_decision": "include",
                "audit_comments": row.get("comments") or row.get("reason"),
            })
    return {"agreed_include": agreed, "disputes": disputes}


def validate_adjudication(doc: Any, disputes: list[dict] | tuple[dict, ...]) -> Any:
    if not isinstance(doc, dict) or set(doc) != {"adjudications"} or not isinstance(doc["adjudications"], list):
        raise EvidenceError("adjudication must contain exactly an adjudications list")
    expected = [(d.get("evidence_id"), d.get("card_tag")) for d in disputes]
    actual = []
    for i, row in enumerate(doc["adjudications"]):
        if not isinstance(row, dict):
            raise EvidenceError(f"adjudications[{i}] must be a mapping")
        if set(row) != {"evidence_id", "card_tag", "decision", "reason"}:
            raise EvidenceError(f"adjudications[{i}] has invalid fields")
        if row["decision"] not in {"include", "exclude"}:
            raise EvidenceError(f"adjudications[{i}].decision must be include or exclude")
        if not isinstance(row["reason"], str) or not row["reason"].strip():
            raise EvidenceError(f"adjudications[{i}].reason must be non-empty")
        actual.append((row.get("evidence_id"), row.get("card_tag")))
    if actual != expected:
        raise EvidenceError(f"adjudication pairs/order must match disputes exactly; expected {expected}, got {actual}")
    return doc
