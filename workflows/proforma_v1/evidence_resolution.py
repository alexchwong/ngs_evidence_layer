"""Pure evidence-resolution policy for proforma-v1.

The model calls and filesystem stay in ``step.py``.  This module owns only the
small policy distinctions that must be shared by diagnosis and PTBG evidence
resolution: cumulative failed-match context, rejected-card exclusion, and the
post-exhaustion fallback for a supplied morphologic diagnosis.
"""
from __future__ import annotations

from copy import deepcopy

PRIMARY_DIAGNOSIS_IDS = {"DX-WHO5", "DX-ICC"}


def rejected_card_ids(failures):
    """Return rejected card IDs in first-seen order."""
    out = []
    for row in failures or []:
        card_id = row.get("card_id")
        if card_id and card_id not in out:
            out.append(card_id)
    return out


def remaining_candidate_ids(item):
    """Candidates still eligible after all prior semantic audit failures."""
    rejected = set(rejected_card_ids(item.get("failures") or []))
    return [cid for cid in item.get("candidate_card_ids") or [] if cid not in rejected]


def public_match_item(item, tag_by_id):
    """Model-facing evidence item with cumulative audit feedback using tags only."""
    prior = []
    for row in item.get("failures") or []:
        card_id = row.get("card_id")
        prior.append(
            {
                "attempt": row.get("attempt"),
                "rejected_card_tag": f"[card:{tag_by_id[card_id]}]" if card_id else None,
                "audit_feedback": list(row.get("comments") or []),
            }
        )
    out = {
        "evidence_id": item["evidence_id"],
        "schema_id": item["schema_id"],
        "reason": item["reason"],
        "candidate_card_tags": [f"[card:{tag_by_id[cid]}]" for cid in remaining_candidate_ids(item)],
    }
    if prior:
        out["prior_failed_matches"] = prior
    return out


def is_primary_diagnosis(element):
    return element.get("schema_id") in PRIMARY_DIAGNOSIS_IDS


def has_supplied_morphology(element):
    return (
        is_primary_diagnosis(element)
        and element.get("morphologic_diagnosis_origin") == "supplied"
        and bool(str(element.get("starting_morphologic_diagnosis") or "").strip())
    )


def retain_supplied_morphology(element):
    """Return an uncited primary-diagnosis element at the supplied morphology.

    Unsupported molecular/cytogenetic reasoning is deliberately removed from
    the reportable source.  Dissent retains the failed reasoning and evidence
    attempts separately.
    """
    if not has_supplied_morphology(element):
        return None
    diagnosis = str(element["starting_morphologic_diagnosis"]).strip()
    clone = deepcopy(element)
    clone["statement"] = f'{element.get("framework_label", "Diagnosis")} classification: {diagnosis}.'
    clone["reason"] = "The supplied morphologic diagnosis is retained unchanged."
    source = dict(clone.get("source") or {})
    source["diagnosis"] = diagnosis
    source["reason"] = clone["reason"]
    source["variants"] = []
    source["diagnostic_effect"] = "unchanged"
    clone["source"] = source
    clone["variants"] = []
    clone["evidence"] = None
    clone["evidence_resolution"] = "supplied_morphology_retained"
    return clone


def exhaustion_policy(element):
    """Return one of: fallback_supplied, unresolved, suppress."""
    if is_primary_diagnosis(element):
        return "fallback_supplied" if has_supplied_morphology(element) else "unresolved"
    return "suppress"
