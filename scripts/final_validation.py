#!/usr/bin/env python3
"""Compatibility CLI for phase-scoped deterministic validation."""
import argparse
import json
import sys
from pathlib import Path

from phase_validation import phase1, phase2, phase4

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
    """Dispatch to the canonical validator owned by the active/consuming phase."""
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
    if phase == 1:
        return phase1.validate_phase_files(
            metadata_path=metadata_path, census_path=census_path
        )
    if phase == 2:
        return phase2.validate_phase_files(
            metadata_path=metadata_path,
            census_path=census_path,
            source_path=source_path,
            provisional_path=provisional_path,
        )
    if phase == 3:
        # Phase 3 has no prompt validator. Phase 4 owns deterministic validation
        # of its incoming Phase 3 review before adjudication/finalization.
        return phase4.validate_review_files(
            provisional_path=provisional_path, review_path=review_path
        )
    return phase4.validate_phase_files(
        metadata_path=metadata_path,
        census_path=census_path,
        source_path=source_path,
        provisional_path=provisional_path,
        review_path=review_path,
        final_path=final_path,
    )


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
        sys.exit(f"PHASE {args.phase} VALIDATION FAILED:\n" + "\n".join(errors))
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(json.dumps({"valid": True, **report}, sort_keys=True))


if __name__ == "__main__":
    main()
