#!/usr/bin/env python3
"""Validate a complete Phase 3 review against its provisional package."""
import argparse
import sys

from package_validation import read_json, validate_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", required=True, help="path to paper.review-001.json")
    parser.add_argument("--provisional", required=True, help="path to paper.provisional-001.json")
    args = parser.parse_args()
    try:
        review = read_json(args.review, "review")
        provisional = read_json(args.provisional, "provisional package")
        errors = validate_review(review, provisional)
    except ValueError as exc:
        sys.exit(f"REVIEW VALIDATION FAILED:\n- {exc}")
    if errors:
        sys.exit("REVIEW VALIDATION FAILED:\n" + "\n".join(f"- {error}" for error in errors))
    print("OK: review matches provisional package")


if __name__ == "__main__":
    main()