#!/usr/bin/env python3
"""Self-contained Phase 5 revision validators injected into the ChatGPT prompt.

These functions are an online artifact-quality gate. Local apply/confirm code reruns
all security-critical checks before any accepted corpus state is changed.
"""
import hashlib
import json
import re

IMMUTABLE_CARD_FIELDS = (
    "card_id",
    "genes",
    "diseases",
    "disease_ancestors",
    "category",
    "evidence_tier",
    "secondary_citation",
)


def canonical_sha256(document):
    payload = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def revision_sha256(card, evidence):
    return canonical_sha256({"card": card, "evidence": evidence})


def _normalise(text, markdown=False):
    text = str(text).replace("\r\n", "\n").replace("\r", "\n")
    if markdown:
        lines = []
        for line in text.splitlines():
            if re.match(r"^\s*\|?(?:\s*:?-+:?\s*\|)+\s*$", line):
                continue
            lines.append(line.replace("|", " "))
        text = "\n".join(lines)
    return re.sub(r"\s+", " ", text).strip()


def _target_map(targets):
    return {item.get("card_id"): item for item in targets.get("targets", [])}


def _provisional_map(provisional):
    return {item.get("card_id"): item for item in provisional.get("revisions", [])}


def validate_revision_provisional(phase5, targets, provisional, paper_text):
    errors = []
    if phase5.get("phase") != 5 or phase5.get("mode") != "revision":
        errors.append("phase5.json is not revision mode")
        return errors
    if provisional.get("schema_version") != "1.0" or provisional.get("phase") != 5:
        errors.append("revision provisional must have schema_version 1.0 and phase 5")
    if provisional.get("mode") != "revision":
        errors.append("revision provisional mode must be revision")
    if provisional.get("publication_key") != phase5.get("publication_key"):
        errors.append("provisional publication_key does not match phase5.json")
    if provisional.get("paper_id") != targets.get("paper_id"):
        errors.append("provisional paper_id does not match targets")
    if provisional.get("round") != 1:
        errors.append("revision provisional round must be 1")
    if not isinstance(provisional.get("extraction_model"), str) or not provisional.get("extraction_model", "").strip():
        errors.append("revision provisional extraction_model is required")

    target_map = _target_map(targets)
    allowed = set(phase5.get("target_card_ids") or [])
    if allowed != set(target_map):
        errors.append("target file card IDs do not exactly match phase5 target_card_ids")
    revisions = provisional.get("revisions")
    if not isinstance(revisions, list) or not revisions:
        errors.append("revision provisional must contain at least one changed card")
        return errors
    ids = [item.get("card_id") for item in revisions]
    if len(ids) != len(set(ids)):
        errors.append("revision provisional contains duplicate card IDs")
    off_target = sorted(set(ids) - allowed)
    if off_target:
        errors.append("revision provisional contains off-target cards: " + ", ".join(off_target))

    source = _normalise(paper_text, markdown=True)
    for item in revisions:
        card_id = item.get("card_id")
        if card_id not in target_map:
            continue
        if set(item) != {"card_id", "replacement_card", "replacement_evidence", "revision_sha256"}:
            errors.append(f"{card_id}: revision item has unexpected or missing fields")
            continue
        original = target_map[card_id]
        card = item.get("replacement_card")
        evidence = item.get("replacement_evidence")
        if not isinstance(card, dict) or not isinstance(evidence, dict):
            errors.append(f"{card_id}: replacement card and evidence must be objects")
            continue
        if card.get("card_id") != card_id or evidence.get("card_id") != card_id:
            errors.append(f"{card_id}: replacement card/evidence card_id mismatch")
        if set(card) != set(original.get("card") or {}):
            errors.append(f"{card_id}: replacement card fields must exactly match the original card fields")
        for field in IMMUTABLE_CARD_FIELDS:
            if card.get(field) != (original.get("card") or {}).get(field):
                errors.append(f"{card_id}: immutable card field changed: {field}")
        if card == original.get("card") and evidence == original.get("evidence"):
            errors.append(f"{card_id}: replacement is identical to the accepted card/evidence")
        expected_hash = revision_sha256(card, evidence)
        if item.get("revision_sha256") != expected_hash:
            errors.append(f"{card_id}: revision_sha256 does not match replacement content")
        fragments = evidence.get("fragments") if isinstance(evidence, dict) else None
        if not isinstance(fragments, list) or not fragments:
            errors.append(f"{card_id}: replacement evidence requires fragments")
        else:
            for fragment in fragments:
                quote = _normalise((fragment or {}).get("quote", ""), markdown=True)
                fragment_id = (fragment or {}).get("fragment_id", "?")
                if not quote:
                    errors.append(f"{card_id}/{fragment_id}: evidence quote is empty")
                elif quote not in source:
                    errors.append(f"{card_id}/{fragment_id}: evidence quote not found verbatim in paper.md")
    return errors


def validate_revision_review(phase5, targets, provisional, review):
    errors = []
    if review.get("schema_version") != "1.0" or review.get("phase") != 5:
        errors.append("Phase 5 revision review must have schema_version 1.0 and phase 5")
    if review.get("mode") != "revision":
        errors.append("Phase 5 revision review mode must be revision")
    if review.get("publication_key") != phase5.get("publication_key"):
        errors.append("review publication_key does not match phase5.json")
    if review.get("paper_id") != provisional.get("paper_id"):
        errors.append("review paper_id does not match provisional")
    if review.get("round") != provisional.get("round"):
        errors.append("review round does not match provisional")
    if review.get("extraction_model_reviewed") != provisional.get("extraction_model"):
        errors.append("review extraction_model_reviewed does not match provisional")
    if review.get("reviewer_model") == provisional.get("extraction_model"):
        errors.append("reviewer model must differ from Phase 5 extraction model")
    if not isinstance(review.get("reviewer_model"), str) or not review.get("reviewer_model", "").strip():
        errors.append("reviewer_model is required")

    provisional_map = _provisional_map(provisional)
    results = review.get("results")
    if not isinstance(results, list):
        errors.append("review results must be an array")
        return errors
    result_ids = [item.get("card_id") for item in results]
    provisional_ids = [item.get("card_id") for item in provisional.get("revisions", [])]
    if result_ids != provisional_ids:
        errors.append("review results must cover every provisional revision once and preserve order")
    if len(result_ids) != len(set(result_ids)):
        errors.append("review contains duplicate card IDs")
    for result in results:
        card_id = result.get("card_id")
        provisional_item = provisional_map.get(card_id)
        if provisional_item is None:
            continue
        if result.get("revision_sha256") != provisional_item.get("revision_sha256"):
            errors.append(f"{card_id}: review hash does not match current provisional revision")
        verdict = result.get("verdict")
        if verdict not in {"pass", "fail"}:
            errors.append(f"{card_id}: review verdict must be pass or fail")
        if verdict == "fail":
            if not str(result.get("reason", "")).strip():
                errors.append(f"{card_id}: failed review requires reason")
            if not str(result.get("suggested_action", "")).strip():
                errors.append(f"{card_id}: failed review requires suggested_action")
    return errors


def validate_revision_asset(phase5, targets, provisional, review, asset):
    errors = validate_revision_review(phase5, targets, provisional, review)
    if errors:
        return errors
    failed = [result.get("card_id") for result in review.get("results", []) if result.get("verdict") != "pass"]
    if failed:
        errors.append("cannot finalize: review has failed cards: " + ", ".join(failed))
        return errors
    if asset.get("schema_version") != "1.0" or asset.get("phase") != 5:
        errors.append("revision asset must have schema_version 1.0 and phase 5")
    if asset.get("mode") != "revision" or asset.get("operation") != "revise_cards":
        errors.append("revision asset must use mode=revision and operation=revise_cards")
    if asset.get("publication_key") != phase5.get("publication_key"):
        errors.append("revision asset publication_key does not match phase5.json")
    if asset.get("paper_id") != provisional.get("paper_id"):
        errors.append("revision asset paper_id does not match provisional")
    if asset.get("base_final_sha256") != phase5.get("base_final_sha256"):
        errors.append("revision asset base_final_sha256 does not match phase5.json")
    if asset.get("base_census_sha256") != phase5.get("base_census_sha256"):
        errors.append("revision asset base_census_sha256 does not match phase5.json")
    if asset.get("extraction_model") != provisional.get("extraction_model"):
        errors.append("revision asset extraction_model does not match provisional")
    if asset.get("reviewer_model") != review.get("reviewer_model"):
        errors.append("revision asset reviewer_model does not match review")

    provisional_items = provisional.get("revisions", [])
    asset_items = asset.get("revisions")
    if not isinstance(asset_items, list):
        errors.append("revision asset revisions must be an array")
        return errors
    if [item.get("card_id") for item in asset_items] != [item.get("card_id") for item in provisional_items]:
        errors.append("revision asset must preserve the provisional revision card order")
    provisional_map = _provisional_map(provisional)
    for item in asset_items:
        card_id = item.get("card_id")
        if set(item) != {"card_id", "revision_sha256", "replacement_card", "replacement_evidence"}:
            errors.append(f"{card_id}: revision asset item has unexpected or missing fields")
            continue
        source = provisional_map.get(card_id)
        if source is None:
            errors.append(f"{card_id}: revision asset contains card absent from provisional")
            continue
        if item != source:
            errors.append(f"{card_id}: revision asset differs from independently reviewed provisional")
    return errors
