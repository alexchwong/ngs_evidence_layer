"""Generic evidence assignment, audit and adjudication mechanics."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class EvidenceError(ValueError):
    pass


def partition_units(units: list[dict] | tuple[dict, ...], max_units: int) -> list[list[dict]]:
    """Partition ordered semantic units without mutating or splitting a unit."""
    if isinstance(max_units, bool) or not isinstance(max_units, int) or max_units < 1:
        raise EvidenceError("max_units must be a positive integer")
    source = list(units)
    return [source[index:index + max_units] for index in range(0, len(source), max_units)]


def merge_batch_rows(
    units: list[dict] | tuple[dict, ...],
    batch_docs: list[dict] | tuple[dict, ...],
    *,
    container: str,
    id_field: str,
) -> dict:
    """Strictly merge validated batch rows back into global semantic-unit order."""
    expected = [str(unit[id_field]) for unit in units]
    if len(set(expected)) != len(expected):
        raise EvidenceError(f"source units contain duplicate {id_field}(s)")
    expected_set = set(expected)
    by_id: dict[str, dict] = {}
    for batch_number, doc in enumerate(batch_docs, 1):
        rows = doc.get(container) if isinstance(doc, dict) else None
        if not isinstance(rows, list):
            raise EvidenceError(f"{container} batch {batch_number} must contain a {container} list")
        for row_number, row in enumerate(rows):
            if not isinstance(row, dict):
                raise EvidenceError(f"{container} batch {batch_number} row {row_number} must be a mapping")
            identity = str(row.get(id_field))
            if identity not in expected_set:
                raise EvidenceError(f"{container} batch {batch_number} has unknown {id_field} {identity!r}")
            if identity in by_id:
                raise EvidenceError(f"{container} batches duplicate {id_field} {identity!r}")
            by_id[identity] = row
    missing = [identity for identity in expected if identity not in by_id]
    if missing:
        raise EvidenceError(f"{container} batches are missing {id_field}(s): {missing}")
    return {container: [by_id[identity] for identity in expected]}


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
    """Audit only cards positively assigned to this fact.
    False-negative rescue belongs to later evidence-match passes, not to the
    auditor. This keeps the audit surface bounded to matcher-selected cards.
    """
    selected = list(assigned_card_tags or [])
    candidates = list(claim.get("candidate_card_tags") or claim.get("candidate_cards") or [])
    unknown = sorted(set(selected) - set(candidates))
    if unknown:
        raise EvidenceError(f"assignment introduced card(s) outside candidate envelope: {unknown}")
    return selected


def merge_match_passes(items: list[dict], pass_docs: list[dict]) -> tuple[dict, list[str]]:
    """Merge sequential match passes, retrying only facts that remain at zero.
    The first non-empty selection for an evidence item becomes final. Later
    passes are allowed to contain only items still unresolved at zero cards.
    Returns ``(final_doc, zero_evidence_ids)`` in original item order.
    """
    expected = [str(item["evidence_id"]) for item in items]
    by_id = {eid: [] for eid in expected}
    unresolved = set(expected)
    for pass_no, doc in enumerate(pass_docs, 1):
        rows = doc.get("matches") if isinstance(doc, dict) else None
        if not isinstance(rows, list):
            raise EvidenceError(f"match pass {pass_no} must contain a matches list")
        seen = set()
        for row in rows:
            if not isinstance(row, dict):
                raise EvidenceError(f"match pass {pass_no} contains a non-mapping row")
            eid = str(row.get("evidence_id"))
            if eid not in unresolved:
                raise EvidenceError(f"match pass {pass_no} contains non-zero/already-resolved evidence_id {eid!r}")
            if eid in seen:
                raise EvidenceError(f"match pass {pass_no} duplicates evidence_id {eid!r}")
            seen.add(eid)
            tags = list(row.get("card_tags") or [])
            if tags:
                by_id[eid] = tags
                unresolved.remove(eid)
        # A pass may intentionally contain only the currently unresolved subset.
    return {"matches": [{"evidence_id": eid, "card_tags": list(by_id[eid])} for eid in expected]}, [eid for eid in expected if eid in unresolved]


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


def adjudication_disputes(disputes: list[dict] | tuple[dict, ...]) -> list[dict]:
    """Return canonical disputes with stable, deterministic adjudication IDs."""
    supplied = ["dispute_id" in dispute for dispute in disputes]
    if any(supplied) and not all(supplied):
        raise EvidenceError("disputes must either all supply dispute_id or all omit it")
    if all(supplied):
        rows = [dict(dispute) for dispute in disputes]
        identities = [str(row["dispute_id"]) for row in rows]
        if len(set(identities)) != len(identities):
            raise EvidenceError("disputes contain duplicate dispute_id(s)")
        return rows
    return [dict(dispute, dispute_id=f"D{index:04d}") for index, dispute in enumerate(disputes, 1)]


def _validate_adjudication_decision(row: dict, *, index: int) -> None:
    if row.get("decision") not in {"include", "exclude"}:
        raise EvidenceError(f"adjudications[{index}].decision must be include or exclude")
    if not isinstance(row.get("reason"), str) or not row["reason"].strip():
        raise EvidenceError(f"adjudications[{index}].reason must be non-empty")


def validate_adjudication(doc: Any, disputes: list[dict] | tuple[dict, ...]) -> Any:
    """Validate model-owned adjudication answers and restore canonical identity.

    New model output owns ``dispute_id``, ``decision`` and ``reason``, with an
    optional ``amended_reason`` for bounded reason pruning. The
    immutable evidence/card identity and canonical order are restored here from
    the supplied dispute list. Legacy full-row artifacts are accepted on read
    and canonicalised as well so existing runs remain consumable.
    """
    if not isinstance(doc, dict) or set(doc) != {"adjudications"} or not isinstance(doc["adjudications"], list):
        raise EvidenceError("adjudication must contain exactly an adjudications list")

    canonical_disputes = adjudication_disputes(disputes)
    by_id = {row["dispute_id"]: row for row in canonical_disputes}
    by_pair = {(row.get("evidence_id"), row.get("card_tag")): row for row in canonical_disputes}
    answers: dict[str, dict] = {}
    rows = doc["adjudications"]

    new_fields = {"dispute_id", "decision", "reason"}
    new_fields_pruned = {"dispute_id", "decision", "reason", "amended_reason"}
    legacy_fields = {"evidence_id", "card_tag", "decision", "reason"}
    legacy_fields_pruned = {"evidence_id", "card_tag", "decision", "reason", "amended_reason"}
    row_shapes = {frozenset(row) for row in rows if isinstance(row, dict)}
    if any(not isinstance(row, dict) for row in rows):
        index = next(i for i, row in enumerate(rows) if not isinstance(row, dict))
        raise EvidenceError(f"adjudications[{index}] must be a mapping")

    if not rows or row_shapes <= {frozenset(new_fields), frozenset(new_fields_pruned)}:
        for i, row in enumerate(rows):
            if set(row) != new_fields and set(row) != new_fields_pruned:
                raise EvidenceError(f"adjudications[{i}] has invalid fields")
            dispute_id = str(row["dispute_id"])
            if dispute_id not in by_id:
                raise EvidenceError(f"adjudications[{i}] has unknown dispute_id {dispute_id!r}")
            if dispute_id in answers:
                raise EvidenceError(f"adjudications[{i}] duplicates dispute_id {dispute_id!r}")
            _validate_adjudication_decision(row, index=i)
            if "amended_reason" in row and (not isinstance(row["amended_reason"], str) or not row["amended_reason"].strip()):
                raise EvidenceError(f"adjudications[{i}].amended_reason must be non-empty when supplied")
            answers[dispute_id] = row
    elif row_shapes <= {frozenset(legacy_fields), frozenset(legacy_fields_pruned)}:
        # Backward-compatible read path for adjudication artifacts produced by
        # earlier devel revisions. Identity/order are still canonicalised here.
        for i, row in enumerate(rows):
            if set(row) != legacy_fields and set(row) != legacy_fields_pruned:
                raise EvidenceError(f"adjudications[{i}] has invalid fields")
            pair = (row.get("evidence_id"), row.get("card_tag"))
            dispute = by_pair.get(pair)
            if dispute is None:
                raise EvidenceError(f"adjudications[{i}] has unknown evidence/card pair {pair!r}")
            dispute_id = dispute["dispute_id"]
            if dispute_id in answers:
                raise EvidenceError(f"adjudications[{i}] duplicates evidence/card pair {pair!r}")
            _validate_adjudication_decision(row, index=i)
            if "amended_reason" in row and (not isinstance(row["amended_reason"], str) or not row["amended_reason"].strip()):
                raise EvidenceError(f"adjudications[{i}].amended_reason must be non-empty when supplied")
            answers[dispute_id] = row
    else:
        raise EvidenceError("adjudication rows must use one consistent model or legacy field shape")

    missing = [row["dispute_id"] for row in canonical_disputes if row["dispute_id"] not in answers]
    if missing:
        raise EvidenceError(f"adjudication is missing dispute_id(s): {missing}")

    canonical_rows = []
    for dispute in canonical_disputes:
        answer = answers[dispute["dispute_id"]]
        canonical = {
            "evidence_id": dispute.get("evidence_id"),
            "card_tag": dispute.get("card_tag"),
            "decision": answer["decision"],
            "reason": answer["reason"],
        }
        if answer.get("amended_reason"):
            canonical["amended_reason"] = answer["amended_reason"]
        canonical_rows.append(canonical)

    # Mutate the parsed object so every existing consumer sees the deterministic
    # full-row representation without needing workflow-specific glue code.
    doc.clear()
    doc["adjudications"] = canonical_rows
    return doc
