#!/usr/bin/env python3
"""Validate legacy adjudication and append its effective integrated diagnosis to case.md."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.core.retrieval import load_step_json  # noqa: E402
from workflows.legacy_v1.adjudication import normalise_adjudication  # noqa: E402


def effective_diagnosis(adjudication):
    review = adjudication.get("user_review")
    if review == "automatic" or review is None:
        return adjudication.get("diagnostic_label") or adjudication["downstream_filter_disease"]
    return review.get("diagnostic_label") or review["refined_disease"]


def append_integrated_diagnosis(case_path: Path, diagnosis_result: Path, adjudication_result: Path) -> None:
    if not case_path.is_file():
        raise ValueError(f"case file not found: {case_path}")
    step2 = load_step_json(diagnosis_result)
    adjudication_raw = json.loads(adjudication_result.read_text(encoding="utf-8"))
    adjudication = normalise_adjudication(
        step2, adjudication_raw, require_completed_review=True
    )
    if adjudication != adjudication_raw:
        adjudication_result.write_text(
            json.dumps(adjudication, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    diagnosis = effective_diagnosis(adjudication)
    if not isinstance(diagnosis, str) or not diagnosis.strip() or "\n" in diagnosis or "\r" in diagnosis:
        raise ValueError("effective integrated diagnosis must be one non-empty line")
    text = case_path.read_text(encoding="utf-8")
    if any(line.startswith("Integrated diagnosis:") for line in text.splitlines()):
        raise ValueError("case.md already contains an Integrated diagnosis line")
    sentence = f"Integrated diagnosis: {diagnosis.strip()}.\n"
    separator = "" if not text or text.endswith("\n") else "\n"
    with case_path.open("a", encoding="utf-8") as handle:
        handle.write(separator + sentence)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", type=Path, required=True)
    parser.add_argument("--diagnosis-result", type=Path, required=True)
    parser.add_argument("--adjudication-result", type=Path, required=True)
    args = parser.parse_args()
    try:
        append_integrated_diagnosis(args.case, args.diagnosis_result, args.adjudication_result)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(1, f"integrated diagnosis append failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
