#!/usr/bin/env python3
"""Deterministically validate the output product of one workflow phase."""
import argparse
import json
import sys
from pathlib import Path

import package_validation as validation

PHASE_ARGUMENTS = {
    1: ("metadata", "census"),
    2: ("metadata", "census", "source", "provisional"),
    3: ("provisional", "review"),
    4: ("metadata", "census", "source", "provisional", "review", "final"),
}


def _require_paths(phase, paths):
    missing = [name for name in PHASE_ARGUMENTS[phase] if paths.get(name) is None]
    if missing:
        raise ValueError(
            f"phase {phase} requires: " + ", ".join(f"--{name}" for name in missing)
        )


def validate_phase_files(
    *,
    phase,
    metadata_path=None,
    census_path=None,
    source_path=None,
    provisional_path=None,
    review_path=None,
    final_path=None,
):
    """Validate only the product and dependencies owned by ``phase``."""
    paths = {
        "metadata": metadata_path,
        "census": census_path,
        "source": source_path,
        "provisional": provisional_path,
        "review": review_path,
        "final": final_path,
    }
    if phase not in PHASE_ARGUMENTS:
        raise ValueError(f"unsupported phase: {phase}")
    _require_paths(phase, paths)

    errors = []
    warnings = []
    report = {"phase": phase}

    if phase == 1:
        metadata = validation.read_json(metadata_path, "metadata")
        census = validation.read_json(census_path, "census")
        errors.extend(f"metadata: {error}" for error in validation.validate_metadata(metadata))
        errors.extend(f"census: {error}" for error in validation.validate_census(census, metadata))
        report.update({"census_entries": len(census.get("entries", []))})
        return errors, warnings, report

    if phase == 2:
        metadata = validation.read_json(metadata_path, "metadata")
        census = validation.read_json(census_path, "census")
        provisional = validation.read_json(provisional_path, "provisional package")
        source_text = Path(source_path).read_text(encoding="utf-8")
        package_errors, warnings, package_report = validation.validate_package(
            provisional,
            metadata,
            census,
            source_text=source_text,
            require_final=False,
        )
        errors.extend(f"provisional: {error}" for error in package_errors)
        report.update(package_report or {})
        return errors, warnings, report

    if phase == 3:
        provisional = validation.read_json(provisional_path, "provisional package")
        review = validation.read_json(review_path, "Phase 3 review")
        errors.extend(
            f"review: {error}"
            for error in validation.validate_review(review, provisional)
        )
        report.update(
            {
                "cards": len(provisional.get("cards", [])),
                "review_results": len(review.get("card_results", [])),
            }
        )
        return errors, warnings, report

    metadata = validation.read_json(metadata_path, "metadata")
    census = validation.read_json(census_path, "census")
    provisional = validation.read_json(provisional_path, "approved provisional package")
    review = validation.read_json(review_path, "Phase 3 review")
    final = validation.read_json(final_path, "final package")

    errors.extend(
        f"final lineage: {error}"
        for error in validation.validate_final_against_provisional(final, provisional)
    )
    approved_round = (final.get("audit") or {}).get("approved_round")
    if approved_round != provisional.get("round"):
        errors.append("final audit approved_round does not match provisional round")
    if approved_round != review.get("round"):
        errors.append("final audit approved_round does not match review round")
    audit = final.get("audit") or {}
    if audit.get("audit_model") != review.get("reviewer_model"):
        errors.append("final audit_model does not match Phase 3 reviewer_model")
    if audit.get("extraction_model_reviewed") != provisional.get("extraction_model"):
        errors.append(
            "final extraction_model_reviewed does not match provisional extraction_model"
        )
    if review.get("reviewer_model") == provisional.get("extraction_model"):
        errors.append("Phase 3 reviewer model must differ from Phase 2 extraction model")

    source_text = Path(source_path).read_text(encoding="utf-8")
    final_errors, warnings, package_report = validation.validate_package(
        final,
        metadata,
        census,
        source_text=source_text,
        require_final=True,
    )
    errors.extend(f"final: {error}" for error in final_errors)
    report.update(package_report or {})
    return errors, warnings, report


def validate_final_files(**paths):
    """Compatibility wrapper for callers that validate a complete Phase 4 set."""
    return validate_phase_files(phase=4, **paths)


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", type=int, choices=(1, 2, 3, 4), required=True)
    for name in ("metadata", "census", "source", "provisional", "review", "final"):
        parser.add_argument(f"--{name}", type=Path)
    args = parser.parse_args(argv)
    provided = {
        name
        for name in ("metadata", "census", "source", "provisional", "review", "final")
        if getattr(args, name) is not None
    }
    required = set(PHASE_ARGUMENTS[args.phase])
    missing = sorted(required - provided)
    if missing:
        parser.error(
            f"phase {args.phase} requires " + ", ".join(f"--{name}" for name in missing)
        )
    return args


def main(argv=None):
    args = parse_args(argv)
    try:
        errors, warnings, report = validate_phase_files(
            phase=args.phase,
            metadata_path=args.metadata,
            census_path=args.census,
            source_path=args.source,
            provisional_path=args.provisional,
            review_path=args.review,
            final_path=args.final,
        )
    except (OSError, ValueError) as exc:
        sys.exit(f"PHASE {args.phase} VALIDATION FAILED:\n{exc}")
    if errors:
        sys.exit(
            f"PHASE {args.phase} VALIDATION FAILED:\n" + "\n".join(errors)
        )
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(json.dumps({"valid": True, **report}, sort_keys=True))


if __name__ == "__main__":
    main()
