#!/usr/bin/env python3
"""Validate a Phase 3 review against the exact provisional package it rejected."""
import argparse
import sys

from package_validation import read_json, validate_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", required=True, help="path to paper.review-NNN.json")
    parser.add_argument("--provisional", required=True, help="path to paper.provisional-NNN.json")
    parser.add_argument(
        "--require-current-guidance",
        action="store_true",
        help="require suggested_action on every failed card",
    )
    args = parser.parse_args()
    try:
        review = read_json(args.review, "review")
        provisional = read_json(args.provisional, "provisional package")
        errors = validate_review(review, provisional, args.require_current_guidance)
    except ValueError as exc:
        sys.exit(f"REVIEW VALIDATION FAILED:\n- {exc}")
    if errors:
        sys.exit("REVIEW VALIDATION FAILED:\n" + "\n".join(f"- {error}" for error in errors))
    print("OK: review matches provisional package")


if __name__ == "__main__":
    main()