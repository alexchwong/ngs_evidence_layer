#!/usr/bin/env python3
"""Deterministically translate Dublin RxCy marking results into F1-F9 scores."""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation import case_registry  # noqa: E402

DEFAULT_SPEC_PATH = ROOT / "validation" / "docs" / "dublin_functional_criteria.md"
ALLOWED_FAILURE_MODES = {"partial", "omitted", "contradicted"}
CRITERION_ID_RE = re.compile(r"\*\*(R[1-5]C[1-9][0-9]*)\.\*\*")
JSON_BLOCK_RE = re.compile(r"```json\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)


class FunctionalScoringError(ValueError):
    """Raised when the Dublin functional spec or marking output is invalid."""


@dataclass(frozen=True)
class FunctionalSpec:
    schema_version: int
    suite: str
    functions: dict[str, str]
    case_criteria_to_function: dict[str, dict[str, str]]
    source: Path

    @property
    def function_ids(self) -> tuple[str, ...]:
        def key(value: str) -> int:
            match = re.fullmatch(r"F([1-9][0-9]*)", value)
            if not match:
                raise FunctionalScoringError(f"Invalid function identifier {value!r}")
            return int(match.group(1))
        return tuple(sorted(self.functions, key=key))


def _extract_single_json_block(text: str, source: Path) -> dict[str, Any]:
    payloads: list[dict[str, Any]] = []
    for raw in JSON_BLOCK_RE.findall(text):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise FunctionalScoringError(f"{source}: invalid JSON specification: {exc}") from exc
        if isinstance(parsed, dict):
            payloads.append(parsed)
    if len(payloads) != 1:
        raise FunctionalScoringError(
            f"{source}: expected exactly one fenced JSON object; found {len(payloads)}"
        )
    return payloads[0]


def load_spec(path: Path = DEFAULT_SPEC_PATH) -> FunctionalSpec:
    path = Path(path)
    if not path.is_file():
        raise FunctionalScoringError(f"Dublin functional specification not found: {path}")
    payload = _extract_single_json_block(path.read_text(encoding="utf-8"), path)

    expected_keys = {
        "schema_version", "suite", "functions", "case_criteria_to_function"
    }
    if set(payload) != expected_keys:
        raise FunctionalScoringError(
            f"{path}: specification keys must be exactly {sorted(expected_keys)}"
        )
    if payload["schema_version"] != 1:
        raise FunctionalScoringError(
            f"{path}: unsupported schema_version {payload['schema_version']!r}; expected 1"
        )
    if not isinstance(payload["suite"], str) or not payload["suite"].strip():
        raise FunctionalScoringError(f"{path}: suite must be a non-empty string")
    functions = payload["functions"]
    mapping = payload["case_criteria_to_function"]
    if not isinstance(functions, dict) or not functions:
        raise FunctionalScoringError(f"{path}: functions must be a non-empty object")
    if not isinstance(mapping, dict) or not mapping:
        raise FunctionalScoringError(
            f"{path}: case_criteria_to_function must be a non-empty object"
        )

    for function_id, description in functions.items():
        if not re.fullmatch(r"F[1-9]", function_id):
            raise FunctionalScoringError(
                f"{path}: Dublin function identifier must be F1-F9; got {function_id!r}"
            )
        if not isinstance(description, str) or not description.strip():
            raise FunctionalScoringError(
                f"{path}: {function_id} must have a non-empty description"
            )
    if set(functions) != {f"F{i}" for i in range(1, 10)}:
        raise FunctionalScoringError(f"{path}: functions must define exactly F1-F9")

    normalised_mapping: dict[str, dict[str, str]] = {}
    for case_id, criterion_map in mapping.items():
        if not isinstance(case_id, str) or not case_id:
            raise FunctionalScoringError(f"{path}: case IDs must be non-empty strings")
        if not isinstance(criterion_map, dict) or not criterion_map:
            raise FunctionalScoringError(
                f"{path}: Case {case_id} mapping must be a non-empty object"
            )
        normalised_mapping[case_id] = {}
        for criterion_id, function_id in criterion_map.items():
            if not re.fullmatch(r"R[1-5]C[1-9][0-9]*", criterion_id):
                raise FunctionalScoringError(
                    f"{path}: Case {case_id}: invalid criterion ID {criterion_id!r}"
                )
            if function_id not in functions:
                raise FunctionalScoringError(
                    f"{path}: Case {case_id} {criterion_id}: unknown function {function_id!r}"
                )
            normalised_mapping[case_id][criterion_id] = function_id

    return FunctionalSpec(
        schema_version=1,
        suite=payload["suite"],
        functions=dict(functions),
        case_criteria_to_function=normalised_mapping,
        source=path.resolve(),
    )


def _criterion_ids(spec: FunctionalSpec, case_id: str) -> tuple[str, ...]:
    criteria = case_registry.retrieve_marking_criteria(spec.suite, case_id)
    return tuple(CRITERION_ID_RE.findall(criteria))


def validate_mapping(spec: FunctionalSpec) -> None:
    case_ids = case_registry.list_case_ids(spec.suite)
    if set(spec.case_criteria_to_function) != set(case_ids):
        missing = sorted(set(case_ids) - set(spec.case_criteria_to_function))
        extra = sorted(set(spec.case_criteria_to_function) - set(case_ids))
        raise FunctionalScoringError(
            f"{spec.source}: mapping case IDs do not match canonical suite; "
            f"missing={missing}, extra={extra}"
        )

    for case_id in case_ids:
        canonical = _criterion_ids(spec, case_id)
        mapped = spec.case_criteria_to_function[case_id]
        if len(canonical) != len(set(canonical)):
            raise FunctionalScoringError(
                f"Case {case_id}: duplicate canonical criterion ID"
            )
        if set(mapped) != set(canonical):
            missing = sorted(set(canonical) - set(mapped))
            extra = sorted(set(mapped) - set(canonical))
            raise FunctionalScoringError(
                f"Case {case_id}: function map mismatch; missing={missing}, extra={extra}"
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
    spec: FunctionalSpec,
    case_id: str,
    results: dict[str, dict[str, Any]],
) -> None:
    expected = set(_criterion_ids(spec, case_id))
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


def score_case(
    case_id: str,
    marking_text: str,
    spec: FunctionalSpec | None = None,
) -> dict[str, Any]:
    spec = spec or load_spec()
    validate_mapping(spec)
    case_id = case_registry.normalise_selector(spec.suite, case_id)
    results = extract_criterion_results(marking_text)
    validate_criterion_results(spec, case_id, results)

    mapping = spec.case_criteria_to_function[case_id]
    functions: dict[str, Any] = {}
    for function in spec.function_ids:
        criteria = [
            cid for cid, mapped_function in mapping.items()
            if mapped_function == function
        ]
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
        "suite": spec.suite,
        "case": case_id,
        "functional_spec": str(spec.source),
        "functions": functions,
    }


def aggregate(
    case_scores: dict[str, dict[str, Any]],
    spec: FunctionalSpec | None = None,
) -> dict[str, Any]:
    spec = spec or load_spec()
    aggregate_scores: dict[str, Any] = {}
    for function in spec.function_ids:
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
        raise argparse.ArgumentTypeError(
            "use CASE=PATH, for example 1=marking-case-1.md"
        )
    case_id, raw_path = value.split("=", 1)
    case_id = case_id.strip()
    path = Path(raw_path.strip())
    if not case_id or not raw_path.strip():
        raise argparse.ArgumentTypeError(
            "use CASE=PATH with non-empty case and path"
        )
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
    parser.add_argument(
        "--spec",
        type=Path,
        default=DEFAULT_SPEC_PATH,
        help="Dublin functional criteria Markdown specification.",
    )
    parser.add_argument("--output", type=Path, help="Optional JSON output path.")
    args = parser.parse_args(argv)

    try:
        spec = load_spec(args.spec)
        validate_mapping(spec)
        supplied: dict[str, Path] = {}
        for case_id, path in args.result:
            case_id = case_registry.normalise_selector(spec.suite, case_id)
            if case_id in supplied:
                raise FunctionalScoringError(
                    f"duplicate --result for case {case_id}"
                )
            supplied[case_id] = path

        scores: dict[str, dict[str, Any]] = {}
        def case_sort(item: tuple[str, Path]) -> tuple[int, str]:
            case_id = item[0]
            return (int(case_id), case_id) if case_id.isdigit() else (10**9, case_id)

        for case_id, path in sorted(supplied.items(), key=case_sort):
            if not path.is_file():
                raise FunctionalScoringError(
                    f"Case {case_id}: marking output not found: {path}"
                )
            scores[case_id] = score_case(
                case_id,
                path.read_text(encoding="utf-8"),
                spec,
            )

        payload = {
            "suite": spec.suite,
            "functional_spec": str(spec.source),
            "function_definitions": spec.functions,
            "cases": scores,
            "aggregate": aggregate(scores, spec),
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
