#!/usr/bin/env python3
"""Validate adjudication and append its effective integrated diagnosis to case.md."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import retrieve  # noqa: E402


def _effective_diagnosis(adjudication):
    review = adjudication.get("user_review")
    if review == "automatic" or review is None:
        return adjudication.get("diagnostic_label") or adjudication["downstream_filter_disease"]
    return review.get("diagnostic_label") or review["refined_disease"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--diagnosis-result", type=Path, required=True)
    parser.add_argument("--adjudication-result", type=Path, required=True)
    args = parser.parse_args()

    try:
        if not args.case.is_file():
            raise ValueError(f"case file not found: {args.case}")
        step2 = json.loads(args.diagnosis_result.read_text(encoding="utf-8"))
        adjudication = json.loads(args.adjudication_result.read_text(encoding="utf-8"))
        retrieve.validate_adjudication(step2, adjudication, require_completed_review=True)
        diagnosis = _effective_diagnosis(adjudication)
        if not isinstance(diagnosis, str) or not diagnosis.strip() or "\n" in diagnosis or "\r" in diagnosis:
            raise ValueError("effective integrated diagnosis must be one non-empty line")

        text = args.case.read_text(encoding="utf-8")
        if any(line.startswith("Integrated diagnosis:") for line in text.splitlines()):
            raise ValueError("case.md already contains an Integrated diagnosis line")

        sentence = f"Integrated diagnosis: {diagnosis.strip()}.\n"
        separator = "" if not text or text.endswith("\n") else "\n"
        with args.case.open("a", encoding="utf-8") as handle:
            handle.write(separator + sentence)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        sys.exit(f"integrated diagnosis append failed: {exc}")


if __name__ == "__main__":
    main()
