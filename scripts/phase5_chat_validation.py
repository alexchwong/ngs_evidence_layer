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


def deletion_sha256(card_id, card_sha256, evidence_sha256, reason):
    return canonical_sha256(
        {
            "card_id": card_id,
            "card_sha256": card_sha256,
            "evidence_sha256": evidence_sha256,
            "reason": str(reason).strip(),
        }
    )


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


def _provisional_revision_map(provisional):
    return {item.get("card_id"): item for item in provisional.get("revisions", [])}


def _provisional_deletion_map(provisional):
    return {item.get("card_id"): item for item in provisional.get("deletions", [])}


def _provisional_changes(provisional):
    changes = [("modify", item) for item in provisional.get("revisions", [])]
    changes.extend(("delete", item) for item in provisional.get("deletions", []))
    return changes


def validate_revision_provisional(phase5, targets, provisional, paper_text):
    errors = []
    if phase5.get("phase") != 5 or phase5.get("mode") != "revision":
        errors.append("phase5.json is not revision mode")
        return errors
    if provisional.get("schema_version") != "1.1" or provisional.get("phase") != 5:
        errors.append("revision provisional must have schema_version 1.1 and phase 5")
    if provisional.get("mode") != "revision":
        errors.append("revision provisional mode must be revision")
    if provisional.get("publication_key") != phase5.get("publication_key"):
        errors.append("provisional publication_key does not match phase5.json")
    if provisional.get("paper_id") != targets.get("paper_id"):
        errors.append("provisional paper_id does not match targets")
    if provisional.get("round") != 1:
        errors.append("revision provisional round must be 1")
    if not isinstance(provisional.get("extraction_model"), str) or not provisional.get(
        "extraction_model", ""
    ).strip():
        errors.append("revision provisional extraction_model is required")
    target_map = _target_map(targets)
    allowed = set(phase5.get("target_card_ids") or [])
    if allowed != set(target_map):
        errors.append("target file card IDs do not exactly match phase5 target_card_ids")
    revisions = provisional.get("revisions")
    deletions = provisional.get("deletions")
    if not isinstance(revisions, list):
        errors.append("revision provisional revisions must be an array")
        revisions = []
    if not isinstance(deletions, list):
        errors.append("revision provisional deletions must be an array")
        deletions = []
    if not revisions and not deletions:
        errors.append("revision provisional must contain at least one changed card")
        return errors
    revision_ids = [item.get("card_id") for item in revisions]
    deletion_ids = [item.get("card_id") for item in deletions]
    if len(revision_ids) != len(set(revision_ids)):
        errors.append("revision provisional contains duplicate modified card IDs")
    if len(deletion_ids) != len(set(deletion_ids)):
        errors.append("revision provisional contains duplicate deleted card IDs")
    overlap = sorted(set(revision_ids) & set(deletion_ids))
    if overlap:
        errors.append("revision provisional cannot both modify and delete: " + ", ".join(overlap))
    off_target = sorted((set(revision_ids) | set(deletion_ids)) - allowed)
    if off_target:
        errors.append("revision provisional contains off-target cards: " + ", ".join(off_target))
    source = _normalise(paper_text, markdown=True)
    for item in revisions:
        card_id = item.get("card_id")
        if card_id not in target_map:
            continue
        if set(item) != {
            "card_id",
            "replacement_card",
            "replacement_evidence",
            "revision_sha256",
        }:
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
            errors.append(
                f"{card_id}: replacement card fields must exactly match the original card fields"
            )
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
                    errors.append(
                        f"{card_id}/{fragment_id}: evidence quote not found verbatim in paper.md"
                    )
    for item in deletions:
        card_id = item.get("card_id")
        if card_id not in target_map:
            continue
        if set(item) != {"card_id", "reason", "deletion_sha256"}:
            errors.append(f"{card_id}: deletion item has unexpected or missing fields")
            continue
        reason = str(item.get("reason", "")).strip()
        if not reason:
            errors.append(f"{card_id}: deletion reason is required")
        target = target_map[card_id]
        expected_hash = deletion_sha256(
            card_id,
            target.get("card_sha256"),
            target.get("evidence_sha256"),
            reason,
        )
        if item.get("deletion_sha256") != expected_hash:
            errors.append(f"{card_id}: deletion_sha256 does not match prepared target and reason")
    return errors


def validate_revision_review(phase5, targets, provisional, review):
    errors = []
    if review.get("schema_version") != "1.1" or review.get("phase") != 5:
        errors.append("Phase 5 revision review must have schema_version 1.1 and phase 5")
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
    if not isinstance(review.get("reviewer_model"), str) or not review.get(
        "reviewer_model", ""
    ).strip():
        errors.append("reviewer_model is required")
    revision_map = _provisional_revision_map(provisional)
    deletion_map = _provisional_deletion_map(provisional)
    changes = _provisional_changes(provisional)
    results = review.get("results")
    if not isinstance(results, list):
        errors.append("review results must be an array")
        return errors
    expected = [(operation, item.get("card_id")) for operation, item in changes]
    actual = [(item.get("operation"), item.get("card_id")) for item in results]
    if actual != expected:
        errors.append("review results must cover every provisional change once and preserve order")
    if len(actual) != len(set(actual)):
        errors.append("review contains duplicate change results")
    for result in results:
        operation = result.get("operation")
        card_id = result.get("card_id")
        if operation == "modify":
            provisional_item = revision_map.get(card_id)
            if provisional_item is not None and result.get("revision_sha256") != provisional_item.get(
                "revision_sha256"
            ):
                errors.append(f"{card_id}: review hash does not match current provisional revision")
        elif operation == "delete":
            provisional_item = deletion_map.get(card_id)
            if provisional_item is not None and result.get("deletion_sha256") != provisional_item.get(
                "deletion_sha256"
            ):
                errors.append(f"{card_id}: review hash does not match current provisional deletion")
        else:
            errors.append(f"{card_id}: review operation must be modify or delete")
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
    failed = [
        result.get("card_id")
        for result in review.get("results", [])
        if result.get("verdict") != "pass"
    ]
    if failed:
        errors.append("cannot finalize: review has failed cards: " + ", ".join(failed))
        return errors
    if asset.get("schema_version") != "1.1" or asset.get("phase") != 5:
        errors.append("revision asset must have schema_version 1.1 and phase 5")
    if asset.get("mode") != "revision" or asset.get("operation") != "change_cards":
        errors.append("revision asset must use mode=revision and operation=change_cards")
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
    provisional_revisions = provisional.get("revisions", [])
    provisional_deletions = provisional.get("deletions", [])
    asset_revisions = asset.get("revisions")
    asset_deletions = asset.get("deletions")
    if not isinstance(asset_revisions, list):
        errors.append("revision asset revisions must be an array")
        asset_revisions = []
    if not isinstance(asset_deletions, list):
        errors.append("revision asset deletions must be an array")
        asset_deletions = []
    if asset_revisions != provisional_revisions:
        errors.append("revision asset revisions must exactly match the independently reviewed provisional")
    if asset_deletions != provisional_deletions:
        errors.append("revision asset deletions must exactly match the independently reviewed provisional")
    confirmed = asset.get("confirmed_change_set")
    expected_confirmed = {
        "add": [],
        "delete": [item.get("card_id") for item in provisional_deletions],
        "modify": [item.get("card_id") for item in provisional_revisions],
    }
    if confirmed != expected_confirmed:
        errors.append("revision asset confirmed_change_set does not exactly match reviewed changes")
    return errors
