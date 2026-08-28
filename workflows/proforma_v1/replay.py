"""Deterministic replay oracle for proforma-v1.

Fixtures freeze a model-facing response, validator context, prompt identity and
proforma-v1 validation outcome. Replay never calls a model provider.
"""
from __future__ import annotations

import argparse
import importlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from scripts.core import validated_model_task
from workflows.proforma_v1.trace import TraceRecorder, sha256_file, sha256_text

HERE = Path(__file__).resolve().parent
DEFAULT_FIXTURES = HERE / "tests" / "fixtures" / "replay"
INDEX_NAME = "index.json"

OPERATION_IDS = {
    "structure_case": "structure",
    "diagnosis_who5": "diagnosis.who1",
    "diagnosis_icc": "diagnosis.icc",
    "diagnosis_other": "diagnosis.other",
    "prognosis": "prognosis",
    "treatment": "treatment",
    "biomarker": "biomarker",
    "germline": "germline",
    "evidence_match": "evidence.assignment",
    "evidence_audit": "evidence.audit",
    "report_write": "report",
    "report_preservation": "report.preservation",
}


DEPENDENCIES = {
    "structure": [],
    "diagnosis.who1": ["structure"],
    "diagnosis.icc": ["diagnosis.who1"],
    "diagnosis.other": ["structure"],
    "prognosis": ["diagnosis.who1", "diagnosis.icc"],
    "treatment": ["diagnosis.who1", "diagnosis.icc"],
    "biomarker": ["diagnosis.who1", "diagnosis.icc"],
    "germline": ["diagnosis.who1", "diagnosis.icc"],
    "evidence.assignment": ["prognosis", "treatment", "biomarker", "germline"],
    "evidence.audit": ["evidence.assignment"],
    "report": ["evidence.audit"],
    "report.preservation": ["report"],
}


@dataclass(frozen=True)
class ReplayCase:
    case_id: str
    stage: str
    operation_id: str
    response_path: Path
    context_path: Path
    expected_path: Path
    prompt_asset: str | None
    source_workflow: str

    @property
    def response(self) -> str:
        return self.response_path.read_text(encoding="utf-8")

    @property
    def context(self) -> dict[str, Any]:
        value = yaml.safe_load(self.context_path.read_text(encoding="utf-8")) or {}
        if not isinstance(value, dict):
            raise ValueError(f"replay context must be a mapping: {self.context_path}")
        return value

    @property
    def expected(self) -> dict[str, Any]:
        return json.loads(self.expected_path.read_text(encoding="utf-8"))


class ReplayExecutor:
    """Model-executor-shaped response source backed only by frozen fixture files."""

    def __init__(self, cases: list[ReplayCase]):
        self._by_operation: dict[str, list[ReplayCase]] = {}
        for case in cases:
            self._by_operation.setdefault(case.operation_id, []).append(case)
        self._offsets: dict[str, int] = {}

    def complete(self, operation_id: str) -> str:
        rows = self._by_operation.get(operation_id) or []
        index = self._offsets.get(operation_id, 0)
        if index >= len(rows):
            raise KeyError(f"no replay response remaining for logical operation {operation_id!r}")
        self._offsets[operation_id] = index + 1
        return rows[index].response


def _workflow_package(workflow_id: str) -> str:
    from scripts.workflow_registry import load_workflow_metadata

    metadata = load_workflow_metadata(workflow_id)
    package = metadata.get("python_package")
    if not isinstance(package, str) or not package:
        raise ValueError(f"workflow {workflow_id!r} has no python package")
    return package


def _stage_modules(workflow_id: str):
    package = _workflow_package(workflow_id)
    return (
        importlib.import_module(f"{package}.stage_checks"),
        importlib.import_module(f"{package}.stage_spec"),
    )


def _outcome(stage_checks, stage: str, response: str, context: dict[str, Any]) -> dict[str, Any]:
    try:
        result = stage_checks.check(stage, response, context)
    except (validated_model_task.ValidationFailure, ValueError) as exc:
        return {
            "accepted": False,
            "message": str(exc),
            "message_sha256": sha256_text(str(exc)),
        }
    return {
        "accepted": True,
        "message": str(result),
        "message_sha256": sha256_text(str(result)),
    }


def load_cases(root: Path = DEFAULT_FIXTURES) -> list[ReplayCase]:
    root = Path(root)
    index = json.loads((root / INDEX_NAME).read_text(encoding="utf-8"))
    cases = []
    for row in index.get("cases") or []:
        folder = root / row["case_id"]
        cases.append(
            ReplayCase(
                case_id=row["case_id"],
                stage=row["stage"],
                operation_id=row["operation_id"],
                response_path=folder / row["response"],
                context_path=folder / "context.yaml",
                expected_path=folder / "expected.json",
                prompt_asset=row.get("prompt_asset"),
                source_workflow=index["source_workflow"],
            )
        )
    return cases


def replay_case(case: ReplayCase, *, workflow_id: str = "proforma-v1", trace: TraceRecorder | None = None) -> dict[str, Any]:
    stage_checks, _stage_spec = _stage_modules(workflow_id)
    outcome = _outcome(stage_checks, case.stage, case.response, case.context)
    expected = case.expected
    prompt_matches = True
    prompt_sha256 = None
    contract_matches = True
    schema_sha256 = None
    stage_spec_sha256 = None
    _checks, target_spec_module = _stage_modules(workflow_id)
    workflow_root = Path(target_spec_module.__file__).resolve().parent
    spec = target_spec_module.load(case.stage)
    stage_spec_sha256 = sha256_file(spec.path)
    schema_path = workflow_root / "schemas" / spec.schema_name
    schema_sha256 = sha256_file(schema_path)
    contract_matches = (
        schema_sha256 == expected.get("schema_sha256")
        and stage_spec_sha256 == expected.get("stage_spec_sha256")
    )
    if case.prompt_asset:
        prompt_path = workflow_root / "prompts" / case.prompt_asset
        prompt_sha256 = sha256_file(prompt_path)
        prompt_matches = prompt_sha256 == expected.get("prompt_sha256")
    outcome["prompt_matches"] = prompt_matches
    outcome["contract_matches"] = contract_matches
    outcome["prompt_sha256"] = prompt_sha256
    outcome["schema_sha256"] = schema_sha256
    outcome["stage_spec_sha256"] = stage_spec_sha256
    if trace is not None:
        trace.record(
            case.operation_id,
            "model",
            "complete" if outcome["accepted"] else "rejected",
            fixture=case.case_id,
            prompt_asset=case.prompt_asset,
            output_artifact=case.stage,
            model_response_sha256=sha256_file(case.response_path),
            validation_result="accepted" if outcome["accepted"] else "rejected",
            dependencies=DEPENDENCIES.get(case.operation_id, []),
            input_artifacts=["fixture.context"],
            prompt_sha256=prompt_sha256,
            schema_sha256=schema_sha256,
            stage_spec_sha256=stage_spec_sha256,
        )
    return outcome


def capture_reference_fixtures(
    *,
    source_workflow: str = "proforma-v1",
    destination: Path = DEFAULT_FIXTURES,
) -> Path:
    """Freeze every shipped stage characterisation response as a replay interaction."""
    stage_checks, stage_spec = _stage_modules(source_workflow)
    source_root = Path(stage_checks.__file__).resolve().parent
    fixture_root = source_root / "tests" / "fixtures"
    destination = Path(destination)
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)

    rows = []
    for stage in stage_checks.names():
        folder = fixture_root / stage
        if not folder.is_dir():
            continue
        context_source = folder / "context.yaml"
        context = stage_checks.fixture_context(stage)
        spec = stage_spec.load(stage)
        candidates = sorted(
            p for p in folder.iterdir()
            if p.is_file()
            and p.name != "context.yaml"
            and not p.name.endswith(".expected.txt")
            and p.suffix in {".yaml", ".json"}
        )
        for candidate in candidates:
            label = candidate.stem.replace("invalid_", "invalid-").replace("_", "-")
            case_id = f"{stage}--{label}"
            target = destination / case_id
            target.mkdir()
            shutil.copyfile(candidate, target / f"response{candidate.suffix}")
            if context_source.is_file():
                shutil.copyfile(context_source, target / "context.yaml")
            else:
                (target / "context.yaml").write_text("{}\n", encoding="utf-8")
            prompt_source = source_root / "prompts" / spec.prompt if spec.prompt else None
            if prompt_source is not None and prompt_source.is_file():
                prompt_snapshot = prompt_source.read_text(encoding="utf-8").rstrip() + "\n"
                (target / "prompt.md").write_text(prompt_snapshot, encoding="utf-8")
            schema_source = source_root / "schemas" / spec.schema_name
            shutil.copyfile(schema_source, target / "schema.json")
            shutil.copyfile(spec.path, target / "stage.yaml")
            outcome = _outcome(stage_checks, stage, candidate.read_text(encoding="utf-8"), context)
            expected = {
                "source_workflow": source_workflow,
                "stage": stage,
                "operation_id": OPERATION_IDS.get(stage, stage.replace("_", ".")),
                "accepted": outcome["accepted"],
                "message": outcome["message"],
                "message_sha256": outcome["message_sha256"],
                "response_sha256": sha256_file(candidate),
                "context_sha256": sha256_file(context_source) if context_source.is_file() else sha256_text("{}\n"),
                "prompt_sha256": sha256_file(prompt_source) if prompt_source is not None and prompt_source.is_file() else None,
                "schema_sha256": sha256_file(schema_source),
                "stage_spec_sha256": sha256_file(spec.path),
            }
            (target / "expected.json").write_text(json.dumps(expected, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            rows.append({
                "case_id": case_id,
                "stage": stage,
                "operation_id": expected["operation_id"],
                "prompt_asset": spec.prompt,
                "response": f"response{candidate.suffix}",
            })
    index = {
        "schema_version": 1,
        "source_workflow": source_workflow,
        "fixture_kind": "recorded_model_interaction",
        "cases": rows,
    }
    path = destination / INDEX_NAME
    path.write_text(json.dumps(index, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def run_suite(*, workflow_id: str = "proforma-v1", root: Path = DEFAULT_FIXTURES, trace_path: Path | None = None) -> dict[str, Any]:
    cases = load_cases(root)
    trace = TraceRecorder(workflow_id)
    failures = []
    for case in cases:
        actual = replay_case(case, workflow_id=workflow_id, trace=trace)
        expected = case.expected
        if (
            actual["accepted"] != expected["accepted"]
            or actual["message_sha256"] != expected["message_sha256"]
            or not actual.get("prompt_matches", True)
            or not actual.get("contract_matches", True)
        ):
            failures.append({"case_id": case.case_id, "expected": expected, "actual": actual})
    if trace_path is not None:
        trace.write(trace_path)
    return {"workflow": workflow_id, "cases": len(cases), "failures": failures, "trace": trace.document()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture")
    capture.add_argument("--source-workflow", default="proforma-v1")
    capture.add_argument("--destination", type=Path, default=DEFAULT_FIXTURES)
    run = sub.add_parser("run")
    run.add_argument("--workflow", default="proforma-v1")
    run.add_argument("--fixtures", type=Path, default=DEFAULT_FIXTURES)
    run.add_argument("--trace", type=Path)
    args = parser.parse_args(argv)
    if args.command == "capture":
        print(capture_reference_fixtures(source_workflow=args.source_workflow, destination=args.destination))
        return 0
    result = run_suite(workflow_id=args.workflow, root=args.fixtures, trace_path=args.trace)
    print(json.dumps({"workflow": result["workflow"], "cases": result["cases"], "failures": result["failures"]}, indent=2))
    return 1 if result["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
