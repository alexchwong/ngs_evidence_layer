from __future__ import annotations

import json
from pathlib import Path

import pytest

from validation.scripts import package_marking as marking


def _valid_minimal_marking() -> str:
    return """# Validation marking

### R1 Diagnostic integration
**Category:** Fully correct

### R2 Diagnostic refinement
**Category:** Not applicable

### R3 Other applicable functions
**Category:** Not applicable

### R4 Evidence use
**Category:** Not applicable

### R5 Safety and hallucination
**Category:** Not applicable

```json
{
  "criterion_results": {
    "R1C1": {"met": true, "failure_mode": null}
  }
}
```
"""


def _minimal_contract(monkeypatch):
    monkeypatch.setattr(marking, "is_validation_mode", lambda _mode: True)
    monkeypatch.setattr(marking, "normalise_selector", lambda _mode, case: str(case))
    monkeypatch.setattr(marking, "_expected_criterion_ids", lambda _mode, _case: ("R1C1",))


def test_automatic_prompt_fails_before_touching_evaluator_inputs(monkeypatch, tmp_path):
    report = tmp_path / "report-final.md"
    monkeypatch.setattr(
        marking,
        "retrieve_case_input",
        lambda *_args: (_ for _ in ()).throw(AssertionError("case input was touched too early")),
    )
    monkeypatch.setattr(
        marking,
        "retrieve_marking_criteria",
        lambda *_args: (_ for _ in ()).throw(AssertionError("criteria were touched too early")),
    )
    with pytest.raises(FileNotFoundError):
        marking.render_automatic_marking_prompt("nel-validate", "1", report)


def test_marking_validator_requires_exact_criterion_set_and_legal_rubrics(monkeypatch):
    _minimal_contract(monkeypatch)
    valid = marking.validate_marking_output(
        "nel-validate-test",
        "1",
        _valid_minimal_marking(),
        report_digest="abc",
    )
    assert valid["criterion_results"] == {"R1C1": {"met": True, "failure_mode": None}}
    assert valid["rubrics"]["R1"]["category"] == "fully correct"
    assert valid["rubrics"]["R2"]["category"] == "not applicable"

    bad = _valid_minimal_marking().replace('"R1C1"', '"R1C2"')
    with pytest.raises(marking.MarkingValidationError, match="criterion_results mismatch"):
        marking.validate_marking_output("nel-validate-test", "1", bad)


def test_current_marking_is_bound_to_exact_report_sha(monkeypatch, tmp_path):
    _minimal_contract(monkeypatch)
    report = tmp_path / "report-final.md"
    report.write_text("first final report\n", encoding="utf-8")
    digest = marking.report_sha256(report)
    text = _valid_minimal_marking()
    normalized = marking.validate_marking_output(
        "nel-validate-test", "1", text, report_digest=digest
    )
    (tmp_path / "marking.md").write_text(text, encoding="utf-8")
    (tmp_path / "marking.json").write_text(json.dumps(normalized), encoding="utf-8")
    assert marking.marking_is_current(tmp_path, "nel-validate-test", "1") is True

    report.write_text("changed final report\n", encoding="utf-8")
    assert marking.marking_is_current(tmp_path, "nel-validate-test", "1") is False


def test_batch_marking_markdown_contains_dublin_functional_aggregate():
    import nel

    rendered = nel._batch_marking_markdown(
        {
            "suite": "nel-validate-dublin",
            "status": "complete",
            "marked": 1,
            "total": 1,
            "criterion_failure_modes": {"partial": 0, "omitted": 0, "contradicted": 0},
            "cases": [
                {
                    "case_id": "001-1",
                    "source_case_id": "1",
                    "marking_status": "complete",
                    "rubrics": {f"R{i}": {"category": "fully correct"} for i in range(1, 6)},
                }
            ],
            "functional": {
                "function_definitions": {"F1": "Diagnostic integration"},
                "cases": {
                    "001-1": {
                        "functions": {
                            "F1": {"result": "met"},
                            **{f"F{i}": {"result": "not_applicable"} for i in range(2, 10)},
                        }
                    }
                },
                "aggregate": {
                    "F1": {"met": 1, "applicable": 1, "proportion": 1.0},
                    **{f"F{i}": {"met": 0, "applicable": 0, "proportion": None} for i in range(2, 10)},
                },
            },
        }
    )
    assert "## Dublin F1–F9 per case" in rendered
    assert "## Dublin F1–F9 aggregate" in rendered
    assert "F1 — Diagnostic integration" in rendered
    assert "| F1 — Diagnostic integration | 1 | 1 | 1.000 |" in rendered


def test_validation_layer_does_not_execute_workflow_models():
    source = (Path(__file__).resolve().parents[1] / "validation" / "scripts" / "package_marking.py").read_text(encoding="utf-8")
    assert "from workflows.proforma_v1" not in source
    assert "._model_call(" not in source


def test_next_call_id_reads_authoritative_call_metadata_not_numbered_directory_names(tmp_path):
    digest = "a" * 64
    root = tmp_path / "model_steps" / "017_validation_marking_aaaaaaaa_01" / "attempts" / "01"
    root.mkdir(parents=True)
    (root / "call.json").write_text(
        json.dumps({"call_id": "validation-marking-aaaaaaaa-01"}), encoding="utf-8"
    )
    assert marking.next_call_id(tmp_path, digest) == "validation-marking-aaaaaaaa-02"


def test_shipped_pipeline_source_of_truth_and_root_copies_include_marking_role():
    root = Path(__file__).resolve().parents[1]
    import yaml
    for name in ("openrouter.yaml", "lmstudio.yaml", "self.yaml"):
        source = root / "workflows" / "proforma_v1" / "pipelines" / name
        target = root / "config" / "pipelines" / name
        assert source.read_bytes() == target.read_bytes()
        doc = yaml.safe_load(source.read_text(encoding="utf-8"))
        roles = doc.get("model_roles") or doc.get("models")
        assert "marking" in roles


def test_batch_marking_includes_per_criterion_failure_counts():
    import nel
    payload = {
        "suite": "nel-validate",
        "status": "partial",
        "marked": 1,
        "total": 2,
        "criterion_failure_modes": {"partial": 1, "omitted": 0, "contradicted": 0},
        "criterion_failure_counts": {
            "R1C2": {"total": 1, "partial": 1, "omitted": 0, "contradicted": 0}
        },
        "cases": [],
    }
    rendered = nel._batch_marking_markdown(payload)
    assert "## Failed criteria" in rendered
    assert "| R1C2 | 1 | 1 | 0 | 0 |" in rendered


def test_failed_marking_allocates_fresh_call_root(monkeypatch, tmp_path):
    digest = "b" * 64
    root = tmp_path / "model_steps" / "004_validation_marking_bbbbbbbb_01" / "attempts" / "01"
    root.mkdir(parents=True)
    (root / "call.json").write_text(
        json.dumps({"call_id": "validation-marking-bbbbbbbb-01"}), encoding="utf-8"
    )
    contract_status = tmp_path / "logs" / marking.MARKING_STATUS
    contract_status.parent.mkdir(parents=True)
    contract_status.write_text(
        json.dumps({
            "schema_version": 1,
            "status": "failed",
            "suite": "nel-validate-test",
            "case": "1",
            "report_sha256": digest,
            "call_id": "validation-marking-bbbbbbbb-01",
        }),
        encoding="utf-8",
    )
    assert marking.next_call_id(tmp_path, digest) == "validation-marking-bbbbbbbb-02"


def test_nonvalidation_prepare_does_not_touch_report_or_evaluator_inputs(monkeypatch, tmp_path):
    monkeypatch.setattr(marking, "is_validation_mode", lambda _mode: False)
    monkeypatch.setattr(
        marking,
        "retrieve_marking_criteria",
        lambda *_args: (_ for _ in ()).throw(AssertionError("criteria should not be read")),
    )
    result = marking.prepare_automatic_marking(tmp_path, "nel-demo", "1")
    assert result == {"status": "not_applicable", "suite": "nel-demo"}


def test_devel_sync_sources_and_managed_root_pipeline_copies_are_in_sync():
    from workflows.proforma_v1 import devel_sync
    assert devel_sync.check() == 0


def test_dublin_missing_functional_artifact_is_not_reported_complete(monkeypatch, tmp_path):
    _minimal_contract(monkeypatch)
    monkeypatch.setattr(marking, "is_validation_mode", lambda _mode: True)
    monkeypatch.setattr(marking, "normalise_selector", lambda _mode, case: str(case))
    # Minimal run state and valid RxCy marking bound to the report.
    state_dir = tmp_path / "intermediates" / "001_run_state"
    state_dir.mkdir(parents=True)
    (state_dir / "proforma-v1-run.json").write_text(
        json.dumps({"mode": marking.DUBLIN_MODE, "validation_case": "1"}), encoding="utf-8"
    )
    report = tmp_path / "report-final.md"
    report.write_text("report\n", encoding="utf-8")
    digest = marking.report_sha256(report)
    text = _valid_minimal_marking()
    normalized = marking.validate_marking_output(marking.DUBLIN_MODE, "1", text, report_digest=digest)
    (tmp_path / "marking.md").write_text(text, encoding="utf-8")
    (tmp_path / "marking.json").write_text(json.dumps(normalized), encoding="utf-8")
    marking._write_marking_status(
        tmp_path, status="complete", suite=marking.DUBLIN_MODE, case="1",
        report_sha256=digest, call_id="validation-marking-test-01",
    )
    state = marking.inspect_marking(tmp_path)
    assert state["status"] == "pending"
    assert state["reason"] == "functional_translation_pending"


def test_batch_status_requires_marking_completion_after_all_reports(monkeypatch, tmp_path):
    from types import SimpleNamespace
    import nel

    batch = SimpleNamespace(
        batch_id="batch-1",
        path=tmp_path,
        manifest={
            "workflow": "proforma-v1",
            "mode": "nel-validate",
            "pipeline": "openrouter",
            "children": [{"case_id": "001", "run_id": "batch-1:001", "title": "Case 1"}],
        },
    )
    state = {
        "status": "complete",
        "children": {"001": {"status": "complete"}},
        "started_at": None,
        "finished_at": "2026-09-04T12:00:00+00:00",
    }
    child = {
        "case_id": "001", "run_id": "batch-1:001", "case_title": "Case 1",
        "batch_status": "complete", "complete": True,
        "marking": {"applicable": True, "status": "failed"},
    }
    monkeypatch.setattr(nel, "_resolve_batch", lambda _batch_id: batch)
    monkeypatch.setattr(nel.run_layout, "load_batch_state", lambda _batch: state)
    monkeypatch.setattr(nel, "_child_row", lambda *_args: dict(child))
    monkeypatch.setattr(nel, "_aggregate_usage", lambda _paths: None)
    monkeypatch.setattr(
        nel, "_aggregate_batch_marking",
        lambda *_args: {"applicable": True, "status": "partial", "marked": 0, "total": 1, "complete": False},
    )

    doc = nel.batch_status("batch-1")
    assert doc["stored_status"] == "complete"
    assert doc["status"] == "marking_incomplete"
    assert doc["complete"] is False
    assert doc["stage"] == "validation_marking"


def test_marking_incomplete_batch_selects_only_unresolved_markers(monkeypatch, tmp_path):
    from types import SimpleNamespace
    import nel

    rows = [
        {"case_id": "001", "run_id": "batch-1:001"},
        {"case_id": "002", "run_id": "batch-1:002"},
    ]
    batch = SimpleNamespace(batch_id="batch-1", path=tmp_path, manifest={"children": rows})
    state = {
        "status": "marking_incomplete",
        "children": {
            "001": {"status": "complete"},
            "002": {"status": "complete"},
        },
    }
    monkeypatch.setattr(
        nel, "_child_needs_marking_retry",
        lambda _batch, row, _state: row["case_id"] == "002",
    )
    selected = nel._selected_batch_children(batch, state)
    assert [row["case_id"] for row in selected] == ["002"]
