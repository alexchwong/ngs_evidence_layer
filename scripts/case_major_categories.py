#!/usr/bin/env python3
"""Render the small authoritative case-major-category list for Step 1B."""
import argparse
import json
from pathlib import Path

import vocab


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write JSON here instead of stdout")
    args = parser.parse_args()
    payload = {
        "case_major_categories": list(vocab.CASE_MAJOR_CATEGORIES),
        "instruction": (
            "Select exactly one case_major_category representing the supplied starting "
            "clinicomorphological major category; do not revise it using molecular results."
        ),
    }
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
