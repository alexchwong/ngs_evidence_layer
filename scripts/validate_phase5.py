#!/usr/bin/env python3
"""Deterministically validate additive or revision Phase 5 artefacts."""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import package_validation as validation
from phase_validation import phase5 as chat_validation


def canonical_sha256(document):
    payload = json.dumps(
        document, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _maps(items, key="card_id"):
    return {item.get(key): item for item in items}


def _derived_coverage(cards):
    return (
        sorted({gene for card in cards for gene in card.get("genes", [])}),
        sorted({disease for card in cards for disease in card.get("diseases", [])}),
    )


def validate_review_only(source_path, provisional_path, review_path):
    provisional = validation.read_json(provisional_path, "Phase 5 provisional package")
    review = validation.read_json(review_path, "Phase 5 review")
    errors = validation.schema_errors(
        provisional, "ingestion_package_schema.json", "Phase 5 provisional"
    )
    errors.extend(validation.validate_review(review, provisional))
    source = validation.normalise(Path(source_path).read_text(encoding="utf-8"), markdown=True)
    for evidence in provisional.get("evidence", []):
        for fragment in evidence.get("fragments", []):
            quote = validation.normalise(fragment.get("quote", ""), markdown=True)
            if quote and quote not in source:
                errors.append(
                    f"{evidence.get('card_id')}/{fragment.get('fragment_id')}: "
                    "fragment not found verbatim in paper.md"
                )
    return errors


def _validate_baseline(
    *, metadata, census, base_census, base_final, marker, source_text,
    accepted_final_path=None, accepted_census_path=None,
):
    errors = []
    warnings = []
    if marker.get("phase") != 5:
        errors.append("phase5.json is not a Phase 5 marker")
    if marker.get("publication_key") != metadata.get("publication_key"):
        errors.append("phase5 publication_key does not match metadata")
    if marker.get("base_final_sha256") != canonical_sha256(base_final):
        errors.append("paper.base.final.json does not match phase5 base_final_sha256")
    if marker.get("base_census_sha256") != canonical_sha256(base_census):
        errors.append("paper.base.census.json does not match phase5 base_census_sha256")
    if census != base_census:
        errors.append("Phase 5 may not modify paper.census.json; use full re-ingest for census changes")
    base_errors, base_warnings, _ = validation.validate_package(
        base_final, metadata, base_census, source_text=source_text, require_final=True
    )
    errors.extend(f"base final: {error}" for error in base_errors)
    warnings.extend(f"base final: {warning}" for warning in base_warnings)
    if accepted_final_path is not None or accepted_census_path is not None:
        if accepted_final_path is None or accepted_census_path is None:
            errors.append("current accepted final and census must be supplied together")
        else:
            envelope = validation.read_json(accepted_final_path, "current accepted package")
            accepted_census = validation.read_json(accepted_census_path, "current accepted census")
            errors.extend(
                f"accepted package: {error}"
                for error in validation.schema_errors(
                    envelope, "accepted_package_schema.json", "accepted package"
                )
            )
            if canonical_sha256(envelope.get("final")) != marker.get("base_final_sha256"):
                errors.append("accepted final changed since Phase 5 preparation")
            if canonical_sha256(accepted_census) != marker.get("base_census_sha256"):
                errors.append("accepted census changed since Phase 5 preparation")
            if envelope.get("final") != base_final:
                errors.append("paper.base.final.json is not the current accepted final")
            if accepted_census != base_census:
                errors.append("paper.base.census.json is not the current accepted census")
    return errors, warnings


def validate_phase5_files(
    *,
    metadata_path,
    census_path,
    source_path,
    base_final_path,
    base_census_path,
    marker_path,
    provisional_path,
    review_path,
    final_path,
    accepted_final_path=None,
    accepted_census_path=None,
):
    """Validate the existing additive Phase 5 workflow."""
    metadata = validation.read_json(metadata_path, "metadata")
    census = validation.read_json(census_path, "census")
    base_census = validation.read_json(base_census_path, "base census")
    base_final = validation.read_json(base_final_path, "base final package")
    marker = validation.read_json(marker_path, "Phase 5 marker")
    provisional = validation.read_json(provisional_path, "Phase 5 provisional package")
    review = validation.read_json(review_path, "Phase 5 review")
    final = validation.read_json(final_path, "Phase 5 merged final package")
    source_text = Path(source_path).read_text(encoding="utf-8")
    errors, warnings = _validate_baseline(
        metadata=metadata,
        census=census,
        base_census=base_census,
        base_final=base_final,
        marker=marker,
        source_text=source_text,
        accepted_final_path=accepted_final_path,
        accepted_census_path=accepted_census_path,
    )
    if marker.get("schema_version") != "1.0":
        errors.append("additive Phase 5 requires phase5 schema_version 1.0")
    if marker.get("mode") not in (None, "additive"):
        errors.append("additive Phase 5 marker has wrong mode")
    if not isinstance(marker.get("supplement"), int) or marker.get("supplement", 0) < 1:
        errors.append("phase5 supplement must be a positive integer")
    provisional_errors, provisional_warnings, _ = validation.validate_package(
        provisional, metadata, census, source_text=source_text, require_final=False
    )
    errors.extend(f"Phase 5 provisional: {error}" for error in provisional_errors)
    warnings.extend(f"Phase 5 provisional: {warning}" for warning in provisional_warnings)
    errors.extend(
        f"Phase 5 review: {error}"
        for error in validation.validate_review(review, provisional)
    )
    if any(result.get("verdict") != "pass" for result in review.get("card_results", [])):
        errors.append("Phase 5 review must pass every proposed card before FINALIZE")
    publication_verdict = (review.get("audit") or {}).get("publication_type_verdict") or {}
    if publication_verdict.get("verdict") != "pass":
        errors.append("Phase 5 review publication_type verdict must pass")
    final_errors, final_warnings, report = validation.validate_package(
        final, metadata, census, source_text=source_text, require_final=True
    )
    errors.extend(f"final: {error}" for error in final_errors)
    warnings.extend(f"final: {warning}" for warning in final_warnings)
    immutable_fields = (
        "schema_version",
        "paper_id",
        "round",
        "extraction_date",
        "extraction_model",
        "paper_nickname",
        "publication_type",
        "publication_type_basis",
        "publication_type_verified_by_phase3",
        "census_entries",
    )
    for field in immutable_fields:
        if final.get(field) != base_final.get(field):
            errors.append(f"Phase 5 may not change final field: {field}")
    base_cards = _maps(base_final.get("cards", []))
    final_cards = _maps(final.get("cards", []))
    supplement_cards = _maps(provisional.get("cards", []))
    base_evidence = _maps(base_final.get("evidence", []))
    final_evidence = _maps(final.get("evidence", []))
    supplement_evidence = _maps(provisional.get("evidence", []))
    for card_id, card in base_cards.items():
        if final_cards.get(card_id) != card:
            errors.append(f"existing card changed or removed: {card_id}")
        if final_evidence.get(card_id) != base_evidence.get(card_id):
            errors.append(f"existing evidence changed or removed: {card_id}")
    added_ids = sorted(set(final_cards) - set(base_cards))
    proposed_ids = sorted(supplement_cards)
    if not added_ids:
        errors.append("Phase 5 must add at least one new card")
    if added_ids != proposed_ids:
        errors.append("new final card IDs must exactly equal Phase 5 provisional card IDs")
    for card_id in proposed_ids:
        if final_cards.get(card_id) != supplement_cards.get(card_id):
            errors.append(f"final Phase 5 card differs from independently reviewed card: {card_id}")
        if final_evidence.get(card_id) != supplement_evidence.get(card_id):
            errors.append(f"final Phase 5 evidence differs from independently reviewed evidence: {card_id}")
    normalised_base = {
        validation.normalise(card.get("interpretation", "")).casefold(): card_id
        for card_id, card in base_cards.items()
    }
    for card_id, card in supplement_cards.items():
        text = validation.normalise(card.get("interpretation", "")).casefold()
        if text in normalised_base:
            errors.append(f"{card_id}: interpretation duplicates existing card {normalised_base[text]}")
    base_audit = base_final.get("audit") or {}
    final_audit = final.get("audit") or {}
    for field in (
        "audit_date",
        "audit_model",
        "extraction_model_reviewed",
        "approved_round",
        "publication_type_verdict",
    ):
        if final_audit.get(field) != base_audit.get(field):
            errors.append(f"Phase 5 may not change existing audit field: {field}")
    base_results = _maps(base_audit.get("results", []))
    final_results = _maps(final_audit.get("results", []))
    for card_id, result in base_results.items():
        if final_results.get(card_id) != result:
            errors.append(f"existing final audit result changed or removed: {card_id}")
    for card_id in added_ids:
        if final_results.get(card_id) != {"card_id": card_id, "verdict": "pass"}:
            errors.append(f"new card requires one passing final audit result: {card_id}")
    if set(final_results) != set(final_cards):
        errors.append("final audit results must cover exactly the merged final cards")
    report = report or {}
    report.update(
        {
            "phase": 5,
            "mode": "additive",
            "supplement": marker.get("supplement"),
            "added_card_ids": added_ids,
            "phase5_extraction_model": provisional.get("extraction_model"),
            "phase5_reviewer_model": review.get("reviewer_model"),
        }
    )
    return errors, warnings, report


def validate_phase5_revision_files(
    *,
    metadata_path,
    census_path,
    source_path,
    base_final_path,
    base_census_path,
    marker_path,
    targets_path,
    provisional_path,
    review_path,
    revision_path,
    final_path,
    accepted_final_path=None,
    accepted_census_path=None,
):
    metadata = validation.read_json(metadata_path, "metadata")
    census = validation.read_json(census_path, "census")
    base_census = validation.read_json(base_census_path, "base census")
    base_final = validation.read_json(base_final_path, "base final package")
    marker = validation.read_json(marker_path, "Phase 5 marker")
    targets = validation.read_json(targets_path, "Phase 5 targets")
    provisional = validation.read_json(provisional_path, "Phase 5 revision provisional")
    review = validation.read_json(review_path, "Phase 5 revision review")
    asset = validation.read_json(revision_path, "Phase 5 revision asset")
    final = validation.read_json(final_path, "Phase 5 revised final package")
    source_text = Path(source_path).read_text(encoding="utf-8")
    errors, warnings = _validate_baseline(
        metadata=metadata,
        census=census,
        base_census=base_census,
        base_final=base_final,
        marker=marker,
        source_text=source_text,
        accepted_final_path=accepted_final_path,
        accepted_census_path=accepted_census_path,
    )
    if marker.get("schema_version") != "1.1" or marker.get("mode") != "revision":
        errors.append("revision Phase 5 requires phase5 schema_version 1.1 and mode revision")
    if not isinstance(marker.get("revision"), int) or marker.get("revision", 0) < 1:
        errors.append("phase5 revision must be a positive integer")
    if not marker.get("target_card_ids"):
        errors.append("revision Phase 5 requires target_card_ids")
    base_cards_for_targets = _maps(base_final.get("cards", []))
    base_evidence_for_targets = _maps(base_final.get("evidence", []))
    target_records = _maps(targets.get("targets", []))
    if set(target_records) != set(marker.get("target_card_ids") or []):
        errors.append("paper.phase5-targets.json does not exactly match the prepared target allowlist")
    marker_targets = _maps(marker.get("targets", []))
    if set(marker_targets) != set(marker.get("target_card_ids") or []):
        errors.append("phase5 target hashes do not exactly cover the prepared target allowlist")
    for card_id in marker.get("target_card_ids") or []:
        marker_target = marker_targets.get(card_id) or {}
        target_record = target_records.get(card_id) or {}
        base_card = base_cards_for_targets.get(card_id)
        base_evidence_item = base_evidence_for_targets.get(card_id)
        if base_card is None or base_evidence_item is None:
            errors.append(f"prepared target missing from base final: {card_id}")
            continue
        if marker_target.get("card_sha256") != canonical_sha256(base_card):
            errors.append(f"{card_id}: prepared base card hash mismatch")
        if marker_target.get("evidence_sha256") != canonical_sha256(base_evidence_item):
            errors.append(f"{card_id}: prepared base evidence hash mismatch")
        if target_record.get("card") != base_card:
            errors.append(f"{card_id}: target card differs from frozen base final")
        if target_record.get("evidence") != base_evidence_item:
            errors.append(f"{card_id}: target evidence differs from frozen base final")
        if target_record.get("card_sha256") != marker_target.get("card_sha256"):
            errors.append(f"{card_id}: target card hash differs from phase5 marker")
        if target_record.get("evidence_sha256") != marker_target.get("evidence_sha256"):
            errors.append(f"{card_id}: target evidence hash differs from phase5 marker")
    errors.extend(
        f"Phase 5 revision provisional: {error}"
        for error in chat_validation.validate_revision_provisional(
            marker, targets, provisional, source_text
        )
    )
    errors.extend(
        f"Phase 5 revision asset: {error}"
        for error in chat_validation.validate_revision_asset(
            marker, targets, provisional, review, asset
        )
    )
    final_errors, final_warnings, report = validation.validate_package(
        final, metadata, census, source_text=source_text, require_final=True
    )
    errors.extend(f"final: {error}" for error in final_errors)
    warnings.extend(f"final: {warning}" for warning in final_warnings)

    base_cards = _maps(base_final.get("cards", []))
    base_evidence = _maps(base_final.get("evidence", []))
    final_cards = _maps(final.get("cards", []))
    final_evidence = _maps(final.get("evidence", []))
    revised = _maps(asset.get("revisions", []))
    revised_ids = [item.get("card_id") for item in asset.get("revisions", [])]
    deleted_ids = [item.get("card_id") for item in asset.get("deletions", [])]
    deleted = set(deleted_ids)
    expected_ids = set(base_cards) - deleted
    if set(final_cards) != expected_ids:
        errors.append("revision Phase 5 final card IDs must equal the base IDs minus reviewed deletions")
    if set(final_evidence) != expected_ids:
        errors.append("revision Phase 5 final evidence IDs must equal the base IDs minus reviewed deletions")
    for card_id in base_cards:
        if card_id in deleted:
            if card_id in final_cards:
                errors.append(f"deleted card still present: {card_id}")
            if card_id in final_evidence:
                errors.append(f"deleted evidence still present: {card_id}")
        elif card_id in revised:
            if final_cards.get(card_id) != revised[card_id].get("replacement_card"):
                errors.append(f"{card_id}: final card differs from reviewed revision asset")
            if final_evidence.get(card_id) != revised[card_id].get("replacement_evidence"):
                errors.append(f"{card_id}: final evidence differs from reviewed revision asset")
        else:
            if final_cards.get(card_id) != base_cards.get(card_id):
                errors.append(f"off-target existing card changed: {card_id}")
            if final_evidence.get(card_id) != base_evidence.get(card_id):
                errors.append(f"off-target existing evidence changed: {card_id}")

    expected_genes, expected_diseases = _derived_coverage(final.get("cards", []))
    if final.get("genes_covered") != expected_genes:
        errors.append("revision Phase 5 genes_covered must be recomputed from final cards")
    if final.get("diseases_covered") != expected_diseases:
        errors.append("revision Phase 5 diseases_covered must be recomputed from final cards")

    base_audit = base_final.get("audit") or {}
    final_audit = final.get("audit") or {}
    for field in set(base_audit) - {"results"}:
        if final_audit.get(field) != base_audit.get(field):
            errors.append(f"revision Phase 5 may not change existing audit field: {field}")
    expected_results = {
        card_id: result
        for card_id, result in _maps(base_audit.get("results", [])).items()
        if card_id not in deleted
    }
    if _maps(final_audit.get("results", [])) != expected_results:
        errors.append("revision Phase 5 audit results must equal base results minus reviewed deletions")

    allowed_top_level_changes = {"cards", "evidence", "audit", "genes_covered", "diseases_covered"}
    for field in set(base_final) - allowed_top_level_changes:
        if final.get(field) != base_final.get(field):
            errors.append(f"revision Phase 5 may not change final field: {field}")
    report = report or {}
    report.update(
        {
            "phase": 5,
            "mode": "revision",
            "revision": marker.get("revision"),
            "revised_card_ids": revised_ids + deleted_ids,
            "modified_card_ids": revised_ids,
            "deleted_card_ids": deleted_ids,
            "phase5_extraction_model": provisional.get("extraction_model"),
            "phase5_reviewer_model": review.get("reviewer_model"),
        }
    )
    return errors, warnings, report


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-only", action="store_true")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--provisional", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--metadata", type=Path)
    parser.add_argument("--census", type=Path)
    parser.add_argument("--base-final", type=Path)
    parser.add_argument("--base-census", type=Path)
    parser.add_argument("--marker", type=Path)
    parser.add_argument("--targets", type=Path)
    parser.add_argument("--revision", type=Path)
    parser.add_argument("--final", type=Path)
    args = parser.parse_args(argv)
    if not args.review_only:
        required = ("metadata", "census", "base_final", "base_census", "marker", "final")
        missing = [name for name in required if getattr(args, name) is None]
        if missing:
            parser.error(
                "full Phase 5 validation requires: "
                + ", ".join("--" + x.replace("_", "-") for x in missing)
            )
    return args


def main(argv=None):
    args = parse_args(argv)
    try:
        if args.review_only:
            errors = validate_review_only(args.source, args.provisional, args.review)
            warnings = []
            report = {"phase": 5, "review_valid": not errors}
        else:
            marker = validation.read_json(args.marker, "Phase 5 marker")
            if marker.get("mode") == "revision":
                if args.targets is None or args.revision is None:
                    raise ValueError("revision validation requires --targets and --revision")
                errors, warnings, report = validate_phase5_revision_files(
                    metadata_path=args.metadata,
                    census_path=args.census,
                    source_path=args.source,
                    base_final_path=args.base_final,
                    base_census_path=args.base_census,
                    marker_path=args.marker,
                    targets_path=args.targets,
                    provisional_path=args.provisional,
                    review_path=args.review,
                    revision_path=args.revision,
                    final_path=args.final,
                )
            else:
                errors, warnings, report = validate_phase5_files(
                    metadata_path=args.metadata,
                    census_path=args.census,
                    source_path=args.source,
                    base_final_path=args.base_final,
                    base_census_path=args.base_census,
                    marker_path=args.marker,
                    provisional_path=args.provisional,
                    review_path=args.review,
                    final_path=args.final,
                )
    except (OSError, ValueError) as exc:
        sys.exit(f"PHASE 5 VALIDATION FAILED:\n{exc}")
    if errors:
        sys.exit("PHASE 5 VALIDATION FAILED:\n" + "\n".join(errors))
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(json.dumps({"valid": True, **report}, sort_keys=True))


if __name__ == "__main__":
    main()
