#!/usr/bin/env python3
"""Deterministically translate Dublin RxCy marking results into F1-F9 scores."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation import case_registry  # noqa: E402

SUITE = "nel-validate-dublin"
FUNCTIONS = tuple(f"F{i}" for i in range(1, 10))
ALLOWED_FAILURE_MODES = {"partial", "omitted", "contradicted"}
CRITERION_ID_RE = re.compile(r"\*\*(R[1-5]C[1-9][0-9]*)\.\*\*")
JSON_BLOCK_RE = re.compile(r"```json\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)

# Every Dublin marking criterion must appear exactly once here.
# F1 integrate NGS findings with the existing diagnosis
# F2 refine/escalate/reclassify diagnosis
# F3 detect a second/concurrent diagnosis
# F4 prognosticate
# F5 identify therapeutically relevant findings
# F6 identify the preferred appropriate molecular MRD target
# F7 identify a potentially germline variant
# F8 identify the associated germline predisposition syndrome
# F9 recognise/apply molecular variables within formal disease-specific
#    prognostic systems used by Dublin (IPSS-M, MIPSS70+/v2.0, CPSS-Mol)
CASE_CRITERION_TO_FUNCTION: dict[str, dict[str, str]] = {
    "1": {
        "R1C1": "F1", "R1C2": "F2", "R2C1": "F4", "R3C1": "F5",
        "R4C1": "F6", "R5C1": "F7", "R5C2": "F8",
    },
    "2": {
        "R1C1": "F1", "R1C2": "F2", "R3C1": "F5", "R4C1": "F6",
    },
    "3": {
        "R1C1": "F1", "R1C2": "F2", "R1C3": "F3", "R2C1": "F4",
        "R4C1": "F6",
    },
    "4": {
        "R1C1": "F1", "R1C2": "F2", "R2C1": "F4", "R2C2": "F9",
        "R5C1": "F7", "R5C2": "F8",
    },
    "5": {
        "R1C1": "F1", "R1C2": "F2", "R1C3": "F3", "R2C1": "F4",
        "R2C2": "F9",
    },
    "6": {
        "R1C1": "F1", "R2C1": "F4", "R2C2": "F9", "R2C3": "F9",
        "R2C4": "F9",
    },
    "7": {
        "R1C1": "F1", "R2C1": "F4", "R2C2": "F9", "R5C1": "F7",
        "R5C2": "F8",
    },
    "8": {
        "R1C1": "F1", "R1C2": "F3", "R2C1": "F4", "R2C2": "F9",
        "R2C3": "F9",
    },
    "9": {
        "R1C1": "F1", "R1C2": "F2", "R2C1": "F4", "R3C1": "F5",
    },
    "10": {
        "R1C1": "F1", "R1C2": "F2", "R2C1": "F4", "R2C2": "F9",
    },
}


class FunctionalScoringError(ValueError):
    """Raised when Dublin marking output or its deterministic mapping is invalid."""


def _criterion_ids(case_id: str) -> tuple[str, ...]:
    criteria = case_registry.retrieve_marking_criteria(SUITE, case_id)
    return tuple(CRITERION_ID_RE.findall(criteria))


def validate_mapping() -> None:
    case_ids = case_registry.list_case_ids(SUITE)
    expected_case_ids = tuple(str(i) for i in range(1, 11))
    if case_ids != expected_case_ids:
        raise FunctionalScoringError(
            f"{SUITE} cases must be exactly {expected_case_ids}; got {case_ids}"
        )
    if set(CASE_CRITERION_TO_FUNCTION) != set(case_ids):
        raise FunctionalScoringError("Dublin function map case IDs do not match canonical suite")

    for case_id in case_ids:
        canonical = _criterion_ids(case_id)
        mapped = CASE_CRITERION_TO_FUNCTION[case_id]
        if len(canonical) != len(set(canonical)):
            raise FunctionalScoringError(f"Case {case_id}: duplicate canonical criterion ID")
        if set(mapped) != set(canonical):
            missing = sorted(set(canonical) - set(mapped))
            extra = sorted(set(mapped) - set(canonical))
            raise FunctionalScoringError(
                f"Case {case_id}: function map mismatch; missing={missing}, extra={extra}"
            )
        bad_functions = sorted(set(mapped.values()) - set(FUNCTIONS))
        if bad_functions:
            raise FunctionalScoringError(
                f"Case {case_id}: invalid functional labels {bad_functions}"
            )


def extract_criterion_results(marking_text: str) -> dict[str, dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for raw in JSON_BLOCK_RE.findall(marking_text):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict) and "criterion_results" in parsed:
            payloads.append(parsed)

    if len(payloads) != 1:
        raise FunctionalScoringError(
            f"Expected exactly one JSON block containing criterion_results; found {len(payloads)}"
        )

    results = payloads[0]["criterion_results"]
    if not isinstance(results, dict):
        raise FunctionalScoringError("criterion_results must be a JSON object")
    return results


def validate_criterion_results(
    case_id: str, results: dict[str, dict[str, Any]]
) -> None:
    expected = set(_criterion_ids(case_id))
    actual = set(results)
    if actual != expected:
        missing = sorted(expected - actual)
        extra = sorted(actual - expected)
        raise FunctionalScoringError(
            f"Case {case_id}: criterion_results mismatch; missing={missing}, extra={extra}"
        )

    for criterion_id, outcome in results.items():
        if not isinstance(outcome, dict):
            raise FunctionalScoringError(
                f"Case {case_id} {criterion_id}: result must be an object"
            )
        if set(outcome) != {"met", "failure_mode"}:
            raise FunctionalScoringError(
                f"Case {case_id} {criterion_id}: result keys must be exactly met and failure_mode"
            )
        met = outcome["met"]
        failure_mode = outcome["failure_mode"]
        if not isinstance(met, bool):
            raise FunctionalScoringError(
                f"Case {case_id} {criterion_id}: met must be boolean"
            )
        if met:
            if failure_mode is not None:
                raise FunctionalScoringError(
                    f"Case {case_id} {criterion_id}: met=true requires failure_mode=null"
                )
        elif failure_mode not in ALLOWED_FAILURE_MODES:
            raise FunctionalScoringError(
                f"Case {case_id} {criterion_id}: met=false requires failure_mode in "
                f"{sorted(ALLOWED_FAILURE_MODES)}"
            )


def score_case(case_id: str, marking_text: str) -> dict[str, Any]:
    validate_mapping()
    case_id = case_registry.normalise_selector(SUITE, case_id)
    results = extract_criterion_results(marking_text)
    validate_criterion_results(case_id, results)

    mapping = CASE_CRITERION_TO_FUNCTION[case_id]
    functions: dict[str, Any] = {}
    for function in FUNCTIONS:
        criteria = [cid for cid, mapped_function in mapping.items() if mapped_function == function]
        if not criteria:
            functions[function] = {
                "result": "not_applicable",
                "criteria": [],
            }
            continue
        failed = [
            {
                "criterion": cid,
                "failure_mode": results[cid]["failure_mode"],
            }
            for cid in criteria
            if not results[cid]["met"]
        ]
        functions[function] = {
            "result": "met" if not failed else "not_met",
            "criteria": criteria,
        }
        if failed:
            functions[function]["failed_criteria"] = failed

    return {
        "suite": SUITE,
        "case": case_id,
        "functions": functions,
    }


def aggregate(case_scores: dict[str, dict[str, Any]]) -> dict[str, Any]:
    aggregate_scores: dict[str, Any] = {}
    for function in FUNCTIONS:
        applicable = 0
        met = 0
        for score in case_scores.values():
            result = score["functions"][function]["result"]
            if result == "not_applicable":
                continue
            applicable += 1
            if result == "met":
                met += 1
        aggregate_scores[function] = {
            "met": met,
            "applicable": applicable,
            "proportion": (met / applicable) if applicable else None,
        }
    return aggregate_scores


def _parse_result_arg(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("use CASE=PATH, for example 1=marking-case-1.md")
    case_id, raw_path = value.split("=", 1)
    case_id = case_id.strip()
    path = Path(raw_path.strip())
    if not case_id or not raw_path.strip():
        raise argparse.ArgumentTypeError("use CASE=PATH with non-empty case and path")
    return case_id, path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--result",
        action="append",
        type=_parse_result_arg,
        required=True,
        metavar="CASE=PATH",
        help="Marking LLM output for one Dublin case; repeat for multiple cases.",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON output path.")
    args = parser.parse_args(argv)

    try:
        validate_mapping()
        supplied: dict[str, Path] = {}
        for case_id, path in args.result:
            case_id = case_registry.normalise_selector(SUITE, case_id)
            if case_id in supplied:
                raise FunctionalScoringError(f"duplicate --result for case {case_id}")
            supplied[case_id] = path

        scores: dict[str, dict[str, Any]] = {}
        for case_id, path in sorted(supplied.items(), key=lambda item: int(item[0])):
            if not path.is_file():
                raise FunctionalScoringError(f"Case {case_id}: marking output not found: {path}")
            scores[case_id] = score_case(case_id, path.read_text(encoding="utf-8"))

        payload = {
            "suite": SUITE,
            "cases": scores,
            "aggregate": aggregate(scores),
        }
        rendered = json.dumps(payload, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered, encoding="utf-8")
        print(rendered, end="")
        return 0
    except (OSError, KeyError, FunctionalScoringError) as exc:
        parser.exit(1, f"functional scoring error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
