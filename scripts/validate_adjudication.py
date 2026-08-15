#!/usr/bin/env python3
"""Validate completed Step 3 adjudication before Step 4."""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import retrieve  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--diagnosis-result", type=Path, required=True)
    parser.add_argument("--adjudication-result", type=Path, required=True)
    args = parser.parse_args()

    try:
        step2 = json.loads(args.diagnosis_result.read_text(encoding="utf-8"))
        adjudication_raw = json.loads(args.adjudication_result.read_text(encoding="utf-8"))
        adjudication = retrieve.normalise_adjudication(
            step2, adjudication_raw, require_completed_review=True
        )
        if adjudication != adjudication_raw:
            args.adjudication_result.write_text(
                json.dumps(adjudication, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        sys.exit(f"adjudication validation failed: {exc}")

    print("OK: adjudication valid for Step 4")


if __name__ == "__main__":
    main()
