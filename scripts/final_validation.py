#!/usr/bin/env python3
"""Deterministically validate a final paper package and its source artefacts."""
import argparse
import json
import sys
from pathlib import Path

import package_validation as validation


def validate_final_files(
    *,
    metadata_path,
    census_path,
    source_path,
    provisional_path,
    review_path,
    final_path,
):
    """Validate the complete Phase 4 file set used by confirmation."""
    metadata_path = Path(metadata_path)
    census_path = Path(census_path)
    source_path = Path(source_path)
    provisional_path = Path(provisional_path)
    review_path = Path(review_path)
    final_path = Path(final_path)

    metadata = validation.read_json(metadata_path, "metadata")
    census = validation.read_json(census_path, "census")
    provisional = validation.read_json(provisional_path, "approved provisional package")
    review = validation.read_json(review_path, "Phase 3 review")
    final = validation.read_json(final_path, "final package")

    errors = [
        f"metadata: {error}"
        for error in validation.validate_metadata(metadata)
    ]
    errors.extend(
        f"census: {error}"
        for error in validation.validate_census(census, metadata)
    )

    provisional_errors, _provisional_warnings, _provisional_report = (
        validation.validate_package(
            provisional,
            metadata,
            census,
            source_text=None,
            require_final=False,
        )
    )
    errors.extend(f"provisional: {error}" for error in provisional_errors)

    review_errors = validation.validate_review(review, provisional)
    errors.extend(f"review: {error}" for error in review_errors)

    errors.extend(
        f"final lineage: {error}"
        for error in validation.validate_final_against_provisional(
            final, provisional
        )
    )

    approved_round = (final.get("audit") or {}).get("approved_round")
    if approved_round != provisional.get("round"):
        errors.append(
            "final audit approved_round does not match provisional round"
        )
    if approved_round != review.get("round"):
        errors.append("final audit approved_round does not match review round")

    audit = final.get("audit") or {}
    if audit.get("audit_model") != review.get("reviewer_model"):
        errors.append(
            "final audit_model does not match Phase 3 reviewer_model"
        )
    if audit.get("extraction_model_reviewed") != provisional.get(
        "extraction_model"
    ):
        errors.append(
            "final extraction_model_reviewed does not match provisional "
            "extraction_model"
        )
    if review.get("reviewer_model") == provisional.get("extraction_model"):
        errors.append(
            "Phase 3 reviewer model must differ from Phase 2 extraction model"
        )

    source_text = source_path.read_text(encoding="utf-8")
    final_errors, warnings, report = validation.validate_package(
        final,
        metadata,
        census,
        source_text=source_text,
        require_final=True,
    )
    errors.extend(f"final: {error}" for error in final_errors)
    return errors, warnings, report


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--provisional", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--final", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        errors, warnings, report = validate_final_files(
            metadata_path=args.metadata,
            census_path=args.census,
            source_path=args.source,
            provisional_path=args.provisional,
            review_path=args.review,
            final_path=args.final,
        )
    except (OSError, ValueError) as exc:
        sys.exit(f"FINAL VALIDATION FAILED:\n{exc}")
    if errors:
        sys.exit("FINAL VALIDATION FAILED:\n" + "\n".join(errors))
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(json.dumps({"valid": True, **report}, sort_keys=True))


if __name__ == "__main__":
    main()
