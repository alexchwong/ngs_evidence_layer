from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from ui import marking_server

ROOT = Path(__file__).resolve().parents[1]


def test_ui_exposes_marking_tab_and_endpoint_loader():
    page = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    assert 'id="markingTab">Marking</button>' in page
    assert 'id="markingView"' in page
    assert "/api/marking?run=" in page
    assert "functionalMarkingHtml" in page
    assert "data-marking-copy" in page


def test_models_view_remains_generic_for_marking_role():
    page = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    assert "logs/model-operations.json" in page
    assert "operation?.label" in page
    assert "meta?.role" in page
    # No marking-specific filtering: the sidecar model call is discovered from
    # the same observability index as every other model role.
    assert "role==='marking'" not in page


def test_single_marking_endpoint_returns_markdown_json_and_functional(monkeypatch, tmp_path):
    (tmp_path / "marking.md").write_text("# Marking\n\nAccepted.\n", encoding="utf-8")
    (tmp_path / "marking.json").write_text(
        json.dumps({"schema_version": 1, "criterion_results": {}}), encoding="utf-8"
    )
    (tmp_path / "functional.json").write_text(
        json.dumps({"schema_version": 1, "functions": {"F1": {"result": "met", "criteria": ["R1C1"]}}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(marking_server.batch, "_top_kind", lambda _ref: "run")
    monkeypatch.setattr(
        marking_server.batch,
        "_nel_json",
        lambda *_args: {
            "mode": "nel-validate-dublin",
            "marking": {
                "applicable": True,
                "status": "complete",
                "suite": "nel-validate-dublin",
                "case": "1",
            },
        },
    )
    monkeypatch.setattr(
        marking_server.batch,
        "_run_location",
        lambda _ref: SimpleNamespace(path=tmp_path),
    )
    monkeypatch.setattr(marking_server, "_functional_definitions", lambda: {"F1": "Diagnostic integration"})

    result = marking_server.marking("run-1")
    assert result["applicable"] is True
    assert result["status"] == "complete"
    assert result["kind"] == "run"
    assert result["case"] == "1"
    assert "# Marking" in result["text"]
    assert result["payload"]["schema_version"] == 1
    assert result["functional"]["functions"]["F1"]["result"] == "met"
    assert result["functional_definitions"]["F1"] == "Diagnostic integration"


def test_batch_marking_endpoint_uses_deterministic_batch_artifacts(monkeypatch, tmp_path):
    (tmp_path / "batch-marking.md").write_text("# Batch validation marking\n", encoding="utf-8")
    (tmp_path / "batch-marking.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "partial",
                "marked": 1,
                "total": 2,
                "functional": {
                    "function_definitions": {"F1": "Diagnostic integration"},
                    "cases": {},
                    "aggregate": {"F1": {"met": 1, "applicable": 1, "proportion": 1.0}},
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(marking_server.batch, "_top_kind", lambda _ref: "batch")
    monkeypatch.setattr(
        marking_server.batch,
        "_nel_json",
        lambda *_args: {
            "mode": "nel-validate-dublin",
            "marking": {"applicable": True, "status": "partial", "marked": 1, "total": 2},
        },
    )
    monkeypatch.setattr(
        marking_server.batch,
        "_batch_location",
        lambda _ref: SimpleNamespace(path=tmp_path),
    )

    result = marking_server.marking("batch-1")
    assert result["kind"] == "batch"
    assert result["status"] == "partial"
    assert result["marked"] == 1
    assert result["total"] == 2
    assert result["functional"]["aggregate"]["F1"]["proportion"] == 1.0
    assert "Batch validation marking" in result["text"]


def test_nonvalidation_marking_endpoint_does_not_read_evaluator_artifacts(monkeypatch, tmp_path):
    monkeypatch.setattr(marking_server.batch, "_top_kind", lambda _ref: "run")
    monkeypatch.setattr(
        marking_server.batch,
        "_nel_json",
        lambda *_args: {
            "mode": "ngs-report",
            "marking": {"applicable": False, "status": "not_applicable"},
        },
    )
    monkeypatch.setattr(
        marking_server.batch,
        "_run_location",
        lambda _ref: SimpleNamespace(path=tmp_path),
    )
    result = marking_server.marking("ordinary-run")
    assert result["applicable"] is False
    assert result["status"] == "not_applicable"
    assert result["text"] == ""
    assert result["payload"] is None
    assert result["functional"] is None


def test_validation_progress_appends_marking_phase_and_allows_retry():
    page = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    assert "function markingPhase(marking,clinicalComplete)" in page
    assert "id:'validation.marking',label:'Marking'" in page
    assert "batch.status==='marking_incomplete'" in page
    assert "btn.textContent='Retry marking'" in page
    assert "['pending','failed','stale']" in page


def test_progress_header_and_phase_text_can_wrap_without_displacing_controls():
    page = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")
    assert ".mid-head{padding:10px 12px" in page
    assert "flex-wrap:wrap;min-width:0}.tabbar" in page
    assert ".attempt{font-family:var(--mono);font-size:10px;color:var(--muted);flex:1 0 100%" in page
    assert ".progress-phase{font:10px/1.25 var(--mono);color:var(--muted);min-width:0;white-space:normal" in page
