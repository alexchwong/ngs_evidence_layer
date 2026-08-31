from __future__ import annotations

import json
from pathlib import Path

from scripts import model_usage


def test_normalize_openrouter_usage_retains_cost_cache_reasoning_and_generation_id():
    document = {
        "id": "gen-123",
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 25,
            "total_tokens": 125,
            "cost": 0.012345,
            "completion_tokens_details": {"reasoning_tokens": 7},
            "prompt_tokens_details": {"cached_tokens": 80, "cache_write_tokens": 10},
            "cost_details": {"upstream_inference_cost": 0.011},
        },
    }
    assert model_usage.normalize_provider_usage(document) == {
        "prompt_tokens": 100,
        "completion_tokens": 25,
        "total_tokens": 125,
        "cost_usd": 0.012345,
        "reasoning_tokens": 7,
        "cached_tokens": 80,
        "cache_write_tokens": 10,
        "cost_details": {"upstream_inference_cost": 0.011},
    }
    assert model_usage.generation_id(document) == "gen-123"


def test_schema_v2_summary_counts_retries_repairs_and_partial_cost(tmp_path: Path):
    path = tmp_path / "model-usage.json"
    model_usage.record_call(
        path, "diagnosis", "m", 1,
        {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12, "cost_usd": 0.01},
        provider="openrouter", duration_ms=100, logical_operation="diagnosis", generation_id_value="gen-a",
    )
    model_usage.record_call(
        path, "diagnosis", "m", 2,
        {"prompt_tokens": 11, "completion_tokens": 3, "total_tokens": 14, "cost_usd": 0.02},
        provider="openrouter", duration_ms=120, logical_operation="diagnosis", generation_id_value="gen-b",
    )
    model_usage.record_call(
        path, "diagnosis-syntax-1", "m", 1,
        {"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5, "cost_usd": 0.003},
        provider="openrouter", duration_ms=30, logical_operation="diagnosis", call_kind="syntax_repair",
    )
    model_usage.record_call(
        path, "treatment", "m", 1, None,
        provider="openrouter", duration_ms=80, logical_operation="treatment", error="network failure",
    )
    summary = model_usage.summarize(path)
    assert summary is not None
    assert summary["schema_version"] == 2
    assert summary["logical_operations"] == 2
    assert summary["physical_calls"] == 4
    assert summary["retry_calls"] == 1
    assert summary["syntax_repair_calls"] == 1
    assert summary["duration_ms"] == 330
    assert summary["totals"]["total_tokens"] == 31
    assert abs(summary["cost"]["amount"] - 0.033) < 1e-12
    assert summary["cost"]["reported_calls"] == 3
    assert summary["cost"]["unreported_calls"] == 1
    assert summary["cost"]["complete"] is False
    assert summary["by_operation"]["diagnosis"]["cost"]["complete"] is True
    ledger = json.loads(path.read_text(encoding="utf-8"))
    assert ledger["schema_version"] == 2
    assert ledger["calls"][0]["generation_id"] == "gen-a"


def test_schema_v1_ledger_remains_readable_and_upgrades_on_append(tmp_path: Path):
    path = tmp_path / "model-usage.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "calls": [{
            "operation": "old",
            "model": "m",
            "attempt": 1,
            "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
        }],
    }), encoding="utf-8")
    summary = model_usage.summarize(path)
    assert summary is not None
    assert summary["totals"]["total_tokens"] == 6
    assert summary["physical_calls"] == 1
    model_usage.record_call(
        path, "new", "m", 1,
        {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3, "cost_usd": 0.001},
        provider="openrouter",
    )
    ledger = json.loads(path.read_text(encoding="utf-8"))
    assert ledger["schema_version"] == 2
    assert len(ledger["calls"]) == 2


def test_cli_cost_format_is_explicitly_partial_for_missing_openrouter_cost():
    summary = {
        "logical_operations": 1,
        "physical_calls": 2,
        "retry_calls": 1,
        "syntax_repair_calls": 0,
        "duration_ms": 1000,
        "reported_calls": 2,
        "unreported_calls": 0,
        "providers": ["openrouter"],
        "totals": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
        "cost": {"currency": "USD", "amount": 0.01, "reported_calls": 1, "unreported_calls": 1, "complete": False},
    }
    lines = model_usage.format_status_lines(summary)
    assert "OpenRouter cost: US$0.010000 (partial; 1 call(s) did not report cost)" in lines


def test_provider_name_detects_openrouter_without_pipeline_name():
    assert model_usage.provider_name(base_url="https://openrouter.ai/api/v1", pipeline="custom") == "openrouter"
