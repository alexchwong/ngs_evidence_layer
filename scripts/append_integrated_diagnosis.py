#!/usr/bin/env python3
"""Append exactly one validated integrated-diagnosis sentence to case.md."""
import argparse
import re
import sys
from pathlib import Path


def _one_line(value, field):
    value = value.strip()
    if not value or "\n" in value or "\r" in value:
        raise ValueError(f"{field} must be one non-empty line")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--diagnosis", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--citation", required=True)
    args = parser.parse_args()

    try:
        if not args.case.is_file():
            raise ValueError(f"case file not found: {args.case}")
        diagnosis = _one_line(args.diagnosis, "diagnosis")
        reason = _one_line(args.reason, "reason").rstrip(". ")
        if not reason:
            raise ValueError("reason must contain text")
        if len(re.findall(r"\S+", reason)) > 20:
            raise ValueError("reason must be 20 words or fewer")
        citation = _one_line(args.citation, "citation")
        if citation.startswith("(") or citation.endswith(")"):
            raise ValueError("citation must be supplied without parentheses")

        text = args.case.read_text(encoding="utf-8")
        if any(line.startswith("Integrated diagnosis:") for line in text.splitlines()):
            raise ValueError("case.md already contains an Integrated diagnosis line")

        sentence = f"Integrated diagnosis: {diagnosis}, based on {reason}. ({citation}).\n"
        separator = "" if not text or text.endswith("\n") else "\n"
        with args.case.open("a", encoding="utf-8") as handle:
            handle.write(separator + sentence)
    except (OSError, ValueError) as exc:
        sys.exit(f"integrated diagnosis append failed: {exc}")


if __name__ == "__main__":
    main()
