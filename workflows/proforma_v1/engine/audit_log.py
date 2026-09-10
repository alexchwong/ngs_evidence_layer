"""Default-workflow semantic audit-log packet, validation and rendering.

Presentation only: this module projects accepted structured clinical artifacts,
report disposition, evidence-card meaning and the existing semantic-dissent
ledger into a compact decision-centric packet for model summarization.  It does
not make or revise clinical decisions.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from workflows.proforma_v1.engine import dissent as workflow_dissent

_CARD_TAG_RE = re.compile(r"\[card:([0-9a-f]{12})\]", re.IGNORECASE)


def _workflow_context(context: dict) -> tuple[Any, Any, Path]:
    ctx = context.get("__workflow_context__") if isinstance(context, dict) else None
    get = ctx.get if ctx is not None and hasattr(ctx, "get") else context.get
    work = Path(context.get("__work__") or getattr(ctx, "work", "."))
    return ctx, get, work


def _variant_display(row: dict | None) -> str:
    row = row or {}
    gene = str(row.get("gene") or "").strip()
    description = str(
        row.get("description")
        or row.get("canonical_display")
        or row.get("variant_id")
        or ""
    ).strip()
    if not description:
        return gene
    if gene and not description.casefold().startswith(gene.casefold()):
        return f"{gene} {description}".strip()
    return description


def _registry(context: dict, get: Any, work: Path) -> dict:
    registry = get("registry") or {}
    if isinstance(registry, dict) and registry:
        return registry
    path = work / "intermediates" / "variant_registry" / "variants.yaml"
    if path.is_file():
        import yaml
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        rows = doc.get("variants") or {}
        return rows if isinstance(rows, dict) else {}
    return {}


def _resolve_text(value: Any, registry: dict) -> str:
    text = " ".join(str(value or "").split())
    if not text:
        return ""
    for vid in sorted(registry, key=lambda item: len(str(item)), reverse=True):
        display = _variant_display(registry.get(vid))
        if display:
            text = re.sub(
                rf"\b{re.escape(str(vid))}\b", display, text,
                flags=re.IGNORECASE,
            )
    return text


def _normal_text(value: Any) -> str:
    return " ".join(str(value or "").split()).casefold()


def _variant_ids(node: dict) -> list[str]:
    values: list[Any] = []
    for key in ("variant", "variant_id", "variants"):
        item = node.get(key)
        if isinstance(item, list):
            values.extend(item)
        elif item not in (None, ""):
            values.append(item)
    seen: list[str] = []
    for value in values:
        text = str(value).strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def _card_projection(card: dict, *, tag: str | None = None) -> dict:
    """Compact model-facing card meaning plus a private merge key."""
    interpretation = " ".join(str(card.get("interpretation") or "").split())
    result: dict[str, Any] = {}
    if tag:
        result["_card_tag"] = tag.lower()
    if interpretation:
        result["interpretation"] = interpretation
    return result


def _card_maps(all_cards: Any, manifest: Any) -> tuple[dict[str, dict], dict[str, dict]]:
    cards = [row for row in (all_cards or []) if isinstance(row, dict) and row.get("card_id")]
    by_id = {str(row["card_id"]): row for row in cards}
    tag_by_id: dict[str, str] = {}
    if isinstance(manifest, dict):
        try:
            from workflows.proforma_v1 import card_identity
            tag_by_id = card_identity.tag_by_id(manifest)
        except Exception:
            tag_by_id = {}
    by_tag = {
        str(tag).lower(): by_id[cid]
        for cid, tag in tag_by_id.items()
        if cid in by_id and tag
    }
    return by_id, by_tag


def _evidence_key(item: dict) -> tuple[str, str]:
    tag = str(item.get("_card_tag") or "").lower()
    if tag:
        return ("tag", tag)
    return ("interpretation", _normal_text(item.get("interpretation")))


def _merge_review(target: dict, review: dict) -> None:
    if not review:
        return
    rows = target.setdefault("review", [])
    if review not in rows:
        rows.append(review)


def _merge_evidence(rows: list[dict], item: dict) -> dict:
    key = _evidence_key(item)
    for existing in rows:
        if _evidence_key(existing) != key:
            continue
        if item.get("interpretation") and not existing.get("interpretation"):
            existing["interpretation"] = item["interpretation"]
        if item.get("final_status"):
            existing["final_status"] = item["final_status"]
        for review in item.get("review") or []:
            _merge_review(existing, review)
        return existing
    rows.append(dict(item))
    return rows[-1]


def _resolve_card_tags(tags: Any, by_tag: dict[str, dict]) -> list[dict]:
    out: list[dict] = []
    for raw in tags or []:
        match = _CARD_TAG_RE.fullmatch(str(raw).strip())
        if not match:
            continue
        tag = match.group(1).lower()
        card = by_tag.get(tag)
        if card:
            _merge_evidence(out, _card_projection(card, tag=tag))
    return out


def _simple_conclusion(node: dict, registry: dict) -> dict:
    """Return scalar/list conclusion fields while excluding reasoning/provenance."""
    ignored = {
        "reason", "evidence_card_tags", "variants", "variant", "variant_id",
        "predisposition_evidence", "event_compatibility", "age", "vaf",
        "personal_history", "family_history", "phenotype", "variant_assessments",
        "prognostic_frameworks", "framework_effects",
    }
    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in ignored or value in (None, "", []):
            continue
        if isinstance(value, (str, int, float, bool)):
            out[key] = _resolve_text(value, registry) if isinstance(value, str) else value
        elif isinstance(value, list) and all(
            isinstance(item, (str, int, float, bool)) for item in value
        ):
            out[key] = [
                _resolve_text(item, registry) if isinstance(item, str) else item
                for item in value
            ]
    return out


def _decision_cards(node: dict, by_tag: dict[str, dict]) -> list[dict]:
    cards = _resolve_card_tags(node.get("evidence_card_tags"), by_tag)
    predisposition = node.get("predisposition_evidence")
    if isinstance(predisposition, dict):
        for card in _resolve_card_tags(predisposition.get("evidence_card_tags"), by_tag):
            _merge_evidence(cards, card)
    return cards


def _walk_reason_decisions(
    domain: str,
    value: Any,
    *,
    path: str,
    registry: dict,
    by_tag: dict[str, dict],
    inherited_vids: list[str] | None = None,
) -> list[dict]:
    rows: list[dict] = []
    if isinstance(value, dict):
        local_vids = _variant_ids(value)
        vids = local_vids or list(inherited_vids or [])
        reason = str(value.get("reason") or "").strip()
        if reason:
            rows.append({
                "decision_id": f"owner:{domain}:{path}",
                "domain": domain,
                "_path": path,
                "_variant_ids": vids,
                "variants": [
                    _variant_display(registry.get(vid)) or _resolve_text(vid, registry)
                    for vid in vids
                ],
                "conclusion": _simple_conclusion(value, registry),
                "reason": _resolve_text(reason, registry),
                "evidence": _decision_cards(value, by_tag),
            })
        for key, child in value.items():
            if key in {"reason", "evidence_card_tags"}:
                continue
            if isinstance(child, (dict, list)):
                rows.extend(_walk_reason_decisions(
                    domain, child,
                    path=f"{path}.{key}",
                    registry=registry,
                    by_tag=by_tag,
                    inherited_vids=vids,
                ))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            if isinstance(child, (dict, list)):
                rows.extend(_walk_reason_decisions(
                    domain, child,
                    path=f"{path}[{index}]",
                    registry=registry,
                    by_tag=by_tag,
                    inherited_vids=inherited_vids,
                ))
    return rows


def _supported_index(supported: Any) -> list[dict]:
    return [row for row in (supported or []) if isinstance(row, dict)]


def _decision_matches_element(decision: dict, element: dict, registry: dict) -> bool:
    if decision.get("domain") != element.get("domain"):
        return False
    if _resolve_text(element.get("reason"), registry) != decision.get("reason"):
        return False
    decision_ids = set(decision.get("_variant_ids") or [])
    element_ids = {str(x) for x in element.get("variants") or []}
    return not decision_ids or not element_ids or decision_ids == element_ids


def _accepted_card(ev: dict, by_id: dict[str, dict], by_tag: dict[str, dict]) -> dict | None:
    cid = str(ev.get("card_id") or "").strip()
    tag_text = str(ev.get("card_tag") or ev.get("runtime_tag") or "").strip()
    match = _CARD_TAG_RE.fullmatch(tag_text)
    tag = match.group(1).lower() if match else ""
    card = by_tag.get(tag) if tag else by_id.get(cid)
    if not card:
        return None
    item = _card_projection(card, tag=tag or None)
    item["final_status"] = "accepted"
    comments = ev.get("audit_comments") or []
    risk = ev.get("risk")
    detail: list[str] = []
    if isinstance(comments, list):
        detail.extend(" ".join(str(x).split()) for x in comments if str(x).strip())
    elif comments not in (None, ""):
        detail.append(" ".join(str(comments).split()))
    if risk not in (None, "", []):
        detail.append(" ".join(str(risk).split()))
    if detail:
        item["review"] = [{"resolution": detail}]
    return item


def _attach_report_disposition(
    decisions: list[dict],
    supported: Any,
    registry: dict,
    by_id: dict[str, dict],
    by_tag: dict[str, dict],
) -> None:
    supported_rows = _supported_index(supported)
    for decision in decisions:
        matches = [
            row for row in supported_rows
            if _decision_matches_element(decision, row, registry)
        ]
        decision["final_disposition"] = "reported" if matches else "considered_not_reported"
        decision["_report_provenance"] = [
            str(row.get("schema_id")) for row in matches if row.get("schema_id")
        ]
        evidence: list[dict] = list(decision.get("evidence") or [])
        for row in matches:
            for ev in row.get("evidence") or []:
                if not isinstance(ev, dict):
                    continue
                item = _accepted_card(ev, by_id, by_tag)
                if item:
                    _merge_evidence(evidence, item)
        decision["evidence"] = evidence


def _dissent_domain(issue: dict) -> str:
    key = str(issue.get("issue_key") or "")
    text = (key + " " + str(issue.get("reviewed_text") or "")).lower()
    if "px-" in text or "prognos" in text:
        return "prognosis"
    if "tx-" in text or "treatment" in text:
        return "treatment"
    if "mrd-" in text or "biomarker" in text:
        return "biomarker"
    if "gl-" in text or "germline" in text:
        return "germline"
    if "dx-" in text or "who" in text or "icc" in text or "diagnos" in text:
        return "diagnosis"
    return "cross-domain"


def _issue_text(issue: dict) -> str:
    chunks = [str(issue.get("issue_key") or ""), str(issue.get("reviewed_text") or "")]
    for event in issue.get("history") or []:
        if not isinstance(event, dict):
            continue
        for key in ("reason", "action", "outcome", "resolution_recommendation"):
            value = event.get(key)
            if isinstance(value, list):
                chunks.extend(str(item) for item in value)
            elif value not in (None, ""):
                chunks.append(str(value))
    return "\n".join(chunks)


def _issue_card_tags(issue: dict) -> list[str]:
    seen: list[str] = []
    for match in _CARD_TAG_RE.finditer(_issue_text(issue)):
        tag = match.group(1).lower()
        if tag not in seen:
            seen.append(tag)
    return seen


def _issue_reason(issue: dict, registry: dict) -> str:
    text = _resolve_text(issue.get("reviewed_text"), registry)
    if not text:
        return ""
    # Evidence dissent normally stores "Reason: ... Card: [...]".  Some older
    # rows store "Statement: ... Reason: ..."; the last Reason field is the
    # closest available owner-reason projection.
    parts = re.split(r"\bReason:\s*", text, flags=re.IGNORECASE)
    if len(parts) > 1:
        text = parts[-1]
    text = re.split(r"\s+Card:\s*\[card:[0-9a-f]{12}\]", text, flags=re.IGNORECASE)[0]
    text = re.sub(r"^Statement:\s*", "", text, flags=re.IGNORECASE)
    return " ".join(text.split()).strip()


def _issue_review(issue: dict, registry: dict) -> dict:
    concerns: list[str] = []
    resolutions: list[str] = []
    for event in issue.get("history") or []:
        if not isinstance(event, dict):
            continue
        event_name = str(event.get("event") or "").casefold()
        reason = event.get("reason") or []
        reason_rows = reason if isinstance(reason, list) else [reason]
        if event_name == "raised":
            for item in reason_rows:
                text = _resolve_text(item, registry)
                if not text:
                    continue
                # The resolver/auditor polarity line is routing metadata; the
                # following sentence contains the human-useful concern.
                if re.fullmatch(r"Resolver:\s*\w+;\s*auditor:\s*\w+\.?", text, flags=re.IGNORECASE):
                    continue
                if text not in concerns:
                    concerns.append(text)
        outcome = event.get("outcome") or []
        action = event.get("action") or []
        outcome_rows = outcome if isinstance(outcome, list) else [outcome]
        action_rows = action if isinstance(action, list) else [action]
        chosen = outcome_rows if any(str(x).strip() for x in outcome_rows) else action_rows
        if event_name == "addressed" or chosen:
            for item in chosen:
                text = _resolve_text(item, registry)
                if text and text not in resolutions:
                    resolutions.append(text)
    review: dict[str, Any] = {"status": str(issue.get("status") or "open")}
    if concerns:
        review["concern"] = concerns
    if resolutions:
        review["resolution"] = resolutions
    return review


def _issue_final_status(issue: dict) -> str | None:
    events = [event for event in issue.get("history") or [] if isinstance(event, dict)]
    for event in reversed(events):
        values: list[str] = []
        for key in ("outcome", "action"):
            value = event.get(key)
            if isinstance(value, list):
                values.extend(str(item) for item in value)
            elif value not in (None, ""):
                values.append(str(value))
        text = " ".join(values).casefold()
        matches = list(re.finditer(r"\bdecision:\s*(include|exclude)\b", text))
        if matches:
            return "accepted" if matches[-1].group(1) == "include" else "rejected"
        matches = list(re.finditer(r"\bdecided to\s+(include|exclude)\b", text))
        if matches:
            return "accepted" if matches[-1].group(1) == "include" else "rejected"
        if re.search(r"\b(?:excluded|suppressed)\s+from\s+(?:the\s+)?report\b", text):
            return "rejected"
    return None


def _match_issue(issue: dict, decisions: list[dict], registry: dict) -> dict | None:
    issue_blob = _normal_text(_issue_text(issue))
    issue_reason = _normal_text(_issue_reason(issue, registry))
    issue_domain = _dissent_domain(issue)
    tags = set(_issue_card_tags(issue))
    scored: list[tuple[int, int, dict]] = []
    for index, decision in enumerate(decisions):
        score = 0
        for schema_id in decision.get("_report_provenance") or []:
            if schema_id and _normal_text(schema_id) in issue_blob:
                score += 120
        reason = _normal_text(decision.get("reason"))
        if issue_reason and reason:
            if issue_reason == reason:
                score += 100
            elif min(len(issue_reason), len(reason)) >= 36 and (
                issue_reason in reason or reason in issue_reason
            ):
                score += 45
        if issue_domain == decision.get("domain"):
            score += 5
        decision_tags = {
            str(item.get("_card_tag") or "").lower()
            for item in decision.get("evidence") or []
            if item.get("_card_tag")
        }
        if tags & decision_tags:
            score += 15
        if score:
            scored.append((score, -index, decision))
    if not scored:
        return None
    scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
    return scored[0][2]


def _fold_dissent(
    decisions: list[dict],
    work: Path,
    registry: dict,
    by_id: dict[str, dict],
    by_tag: dict[str, dict],
) -> list[dict]:
    """Attach dissent as review history; it is not a separate coverage unit."""
    unmatched: list[dict] = []
    for issue in workflow_dissent.doc(work).get("issues") or []:
        if not isinstance(issue, dict):
            continue
        review = _issue_review(issue, registry)
        target = _match_issue(issue, decisions, registry)
        if target is None:
            item = {
                "kind": "review_context",
                "domain": _dissent_domain(issue),
                "review": review,
            }
            statement = _issue_reason(issue, registry) or _resolve_text(issue.get("reviewed_text"), registry)
            if statement:
                item["statement"] = statement
            unmatched.append(item)
            continue

        tags = _issue_card_tags(issue)
        attached = False
        final_status = _issue_final_status(issue)
        for tag in tags:
            evidence = next(
                (row for row in target.get("evidence") or [] if row.get("_card_tag") == tag),
                None,
            )
            if evidence is None:
                card = by_tag.get(tag)
                if card:
                    evidence = _merge_evidence(target.setdefault("evidence", []), _card_projection(card, tag=tag))
            if evidence is not None:
                _merge_review(evidence, review)
                if final_status:
                    evidence["final_status"] = final_status
                attached = True
        if not attached:
            history = target.setdefault("review_history", [])
            if review not in history:
                history.append(review)
    return unmatched


def _public_decision(row: dict) -> dict:
    out: dict[str, Any] = {
        "decision_id": row["decision_id"],
        "domain": row["domain"],
    }
    if row.get("variants"):
        out["variants"] = list(row["variants"])
    if row.get("conclusion"):
        out["conclusion"] = row["conclusion"]
    out["reason"] = row.get("reason") or ""
    out["final_disposition"] = row.get("final_disposition") or "considered_not_reported"
    evidence: list[dict] = []
    for item in row.get("evidence") or []:
        public: dict[str, Any] = {}
        if item.get("interpretation"):
            public["interpretation"] = item["interpretation"]
        if item.get("final_status"):
            public["final_status"] = item["final_status"]
        if item.get("review"):
            public["review"] = item["review"]
        if public:
            evidence.append(public)
    if evidence:
        out["evidence"] = evidence
    if row.get("review_history"):
        out["review_history"] = row["review_history"]
    return out


def render_terminal_failure(work: Path, failure: dict[str, Any]) -> dict[str, Any]:
    """Deterministically render ``audit-log.md`` for a non-resumable run.

    This path is intentionally separate from the normal model-summarized audit
    tail.  It is called only after the workflow has explicitly classified a
    failure as non-retryable, so ordinary/retryable exceptions never create a
    post-mortem audit log.  Rendering is deterministic because a terminal run
    must not depend on another model call merely to explain why it stopped.
    """
    work = Path(work)
    target = work / "audit-log.md"
    legacy = work / "dissent.md"
    if legacy.exists():
        legacy.unlink()

    reviewer = str((failure or {}).get("reviewer") or "workflow").strip()
    message = str((failure or {}).get("message") or "The workflow stopped at a non-resumable failure.").strip()
    sections = [
        "# Audit log",
        "",
        "## Run outcome",
        "",
        "The case did not complete. The workflow reached a non-resumable terminal condition, so automatic resume/retry was forbidden.",
        "",
        f"**Terminal stage:** {reviewer}",
        "",
        f"**Reason:** {message}",
    ]

    issues = workflow_dissent.doc(work).get("issues") or []
    if issues:
        sections.extend(["", "## Semantic review history"] )
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        reviewed = str(issue.get("reviewed_text") or "").strip()
        if not reviewed:
            continue
        sections.extend(["", f"### {reviewed}", ""] )
        for event in issue.get("history") or []:
            if not isinstance(event, dict):
                continue
            stage = str(event.get("stage") or "semantic review").strip()
            kind = str(event.get("event") or "event").strip()
            sections.append(f"**{stage} — {kind}**")
            for key, label in (
                ("reason", "Concern"),
                ("resolution_recommendation", "Recommended action"),
                ("action", "Action"),
                ("outcome", "Outcome"),
            ):
                values = event.get(key)
                values = values if isinstance(values, list) else [values]
                values = [str(item).strip() for item in values if str(item or "").strip()]
                if values:
                    sections.append(f"- {label}: " + "; ".join(values))
        status = str(issue.get("status") or "").strip()
        if status:
            sections.append(f"- Status at termination: {status}")

    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text("\n".join(sections).rstrip() + "\n", encoding="utf-8")
    temporary.replace(target)
    return {"status": "terminal_failure", "issue_count": len(issues), "path": str(target)}


def audit_log_packet(value: Any, context: dict, params: dict) -> Any:
    """Build a compact, decision-centric default-workflow semantic audit packet."""
    _ctx, get, work = _workflow_context(context)
    registry = _registry(context, get, work)
    diagnosis = get("diagnosis") or {}
    domains = get("domains") or {}
    supported = get("supported") or []
    all_cards = get("all_cards") or []
    manifest = get("manifest") or {}
    by_id, by_tag = _card_maps(all_cards, manifest)

    decisions: list[dict] = []
    if diagnosis:
        decisions.extend(_walk_reason_decisions(
            "diagnosis", diagnosis, path="diagnosis", registry=registry, by_tag=by_tag
        ))
    for domain in ("prognosis", "treatment", "biomarker", "germline"):
        if domain in domains:
            decisions.extend(_walk_reason_decisions(
                domain, domains[domain], path=domain, registry=registry, by_tag=by_tag
            ))

    _attach_report_disposition(decisions, supported, registry, by_id, by_tag)
    unmatched_reviews = _fold_dissent(decisions, work, registry, by_id, by_tag)

    ids = [row["decision_id"] for row in decisions]
    if len(ids) != len(set(ids)):
        raise ValueError("audit-log packet contains duplicate decision IDs")

    packet = [_public_decision(row) for row in decisions]
    # Rare non-owner review events are retained for context without becoming
    # coverage units.  No review/dissent ID is exposed to the summarizer.
    packet.extend(unmatched_reviews)
    return packet


def _summary_rows(packet: Any, summary: Any) -> tuple[list[dict], str | None]:
    decisions = packet if isinstance(packet, list) else None
    if not isinstance(decisions, list):
        return [], "audit packet is not a list"
    expected = [
        str(row.get("decision_id") or "").strip()
        for row in decisions
        if isinstance(row, dict) and row.get("decision_id")
    ]
    if not expected:
        return [], None
    rows = summary.get("summaries") if isinstance(summary, dict) else None
    if not isinstance(rows, list) or not rows:
        return [], "summary is unavailable or contains no summaries"
    seen: list[str] = []
    cleaned: list[dict] = []
    for index, row in enumerate(rows, 1):
        if not isinstance(row, dict):
            return [], f"summary row {index} is not an object"
        ids = row.get("source_decision_ids")
        if not isinstance(ids, list) or not ids:
            return [], f"summary row {index} has no source_decision_ids"
        ids = [str(item or "").strip() for item in ids]
        if any(not item for item in ids) or len(ids) != len(set(ids)):
            return [], f"summary row {index} has invalid source_decision_ids"
        domain = str(row.get("domain") or "").strip()
        topic = str(row.get("topic") or "").strip()
        prose = str(row.get("summary") or "").strip()
        if not domain or not topic or not prose:
            return [], f"summary row {index} is missing required fields"
        seen.extend(ids)
        cleaned.append({
            "source_decision_ids": ids,
            "domain": domain,
            "topic": topic,
            "summary": prose,
        })
    if len(seen) != len(set(seen)):
        return [], "a source decision appears in more than one summary row"
    if set(seen) != set(expected):
        missing = sorted(set(expected) - set(seen))
        unknown = sorted(set(seen) - set(expected))
        detail = []
        if missing:
            detail.append("missing " + ", ".join(missing))
        if unknown:
            detail.append("unknown " + ", ".join(unknown))
        return [], "source decision coverage mismatch: " + "; ".join(detail)
    return cleaned, None


def audit_log_validate_summary(value: Any, context: dict, params: dict) -> Any:
    packet = context.get("workflow_audit_log_packet") or []
    count = sum(
        1 for row in packet
        if isinstance(row, dict) and row.get("decision_id")
    ) if isinstance(packet, list) else 0
    if not count:
        return {"status": "pass", "feedback": "", "source_decisions": 0, "summaries": 0}
    rows, error = _summary_rows(packet, context.get("workflow_audit_log_summary"))
    if error:
        return {
            "status": "fail",
            "feedback": (
                "The audit-log summary failed structural coverage validation. "
                + error
                + ". Cover every supplied source decision ID exactly once, individually or in a related group. "
                  "Do not invent IDs or alter clinical decisions."
            ),
            "source_decisions": count,
            "summaries": 0,
        }
    return {
        "status": "pass", "feedback": "",
        "source_decisions": count, "summaries": len(rows),
    }


def _domain_heading(domain: str) -> str:
    return {
        "diagnosis": "Diagnosis",
        "prognosis": "Prognosis",
        "treatment": "Treatment",
        "biomarker": "Biomarker / MRD",
        "germline": "Germline",
        "cross-domain": "Cross-domain review",
    }.get(domain, domain.replace("_", " ").title())


def audit_log_render(value: Any, context: dict, params: dict) -> Any:
    """Render only validated model prose to ``audit-log.md`` for default."""
    _ctx, _get, work = _workflow_context(context)
    packet = context.get("workflow_audit_log_packet") or []
    target = work / "audit-log.md"
    legacy = work / "dissent.md"
    if legacy.exists():
        legacy.unlink()
    count = sum(
        1 for row in packet
        if isinstance(row, dict) and row.get("decision_id")
    ) if isinstance(packet, list) else 0
    if not count:
        if target.exists():
            target.unlink()
        return {"status": "no_items", "source_decisions": 0, "summaries": 0}

    rows, error = _summary_rows(packet, context.get("workflow_audit_log_summary"))
    if error:
        text = (
            "# Audit log\n\n"
            "The structured semantic audit was retained, but the human-readable summary was unavailable.\n"
        )
        target.write_text(text, encoding="utf-8")
        return {
            "status": "summary_unavailable", "reason": error,
            "source_decisions": count, "summaries": 0,
        }

    order = ["diagnosis", "prognosis", "treatment", "biomarker", "germline", "cross-domain"]
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["domain"], []).append(row)
    sections = ["# Audit log"]
    for domain in order + sorted(set(grouped) - set(order)):
        domain_rows = grouped.get(domain) or []
        if not domain_rows:
            continue
        sections.extend(["", f"## {_domain_heading(domain)}"])
        for row in domain_rows:
            sections.extend(["", f"### {row['topic']}", "", row["summary"]])
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + ".tmp")
    temporary.write_text("\n".join(sections).rstrip() + "\n", encoding="utf-8")
    temporary.replace(target)
    return {"status": "summarized", "source_decisions": count, "summaries": len(rows)}


REGISTRY = {
    "audit_log_packet": audit_log_packet,
    "audit_log_validate_summary": audit_log_validate_summary,
    "audit_log_render": audit_log_render,
}


def apply(name: str, value: Any, *, context: dict | None = None, params: dict | None = None) -> Any:
    if name not in REGISTRY:
        raise ValueError(f"unknown audit-log transform {name!r}")
    return REGISTRY[name](value, context or {}, params or {})
