#!/usr/bin/env python3
"""Retrieve bundled clinical case content or post-report marking criteria."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.scripts.bundled_cases import (  # noqa: E402
    bundled_modes,
    list_case_ids,
    retrieve_case_input,
    retrieve_marking_criteria,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("list", "case", "MC"))
    parser.add_argument("selector", nargs="?")
    parser.add_argument("--mode", required=True, choices=bundled_modes())
    args = parser.parse_args()
    try:
        if args.action == "list":
            if args.selector is not None:
                raise ValueError("list does not take a selector")
            print("\n".join(list_case_ids(args.mode)))
        elif args.action == "case":
            if args.selector is None:
                raise ValueError("case requires a selector")
            print(retrieve_case_input(args.mode, args.selector))
        else:
            if args.selector is None:
                raise ValueError("MC requires a selector")
            print(retrieve_marking_criteria(args.mode, args.selector))
    except (OSError, KeyError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
