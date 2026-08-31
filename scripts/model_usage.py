"""Provider-neutral model usage accounting shared by workflow executors.

The per-call ledger is the canonical record. Summaries are derived so CLI, JSON
outputs and a future frontend can consume the same accounting semantics.
"""
from __future__ import annotations

import json
from numbers import Real
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

SCHEMA_VERSION = 2
TOKEN_FIELDS = ("prompt_tokens", "completion_tokens", "total_tokens")


def provider_name(*, base_url: str = "", pipeline: str = "") -> str:
    """Return a stable provider label without adding provider-specific config."""
    host = (urlparse(base_url).hostname or "").lower()
    selector = pipeline.strip().lower()
    if host == "openrouter.ai" or host.endswith(".openrouter.ai") or "openrouter" in selector:
        return "openrouter"
    if selector.startswith("lmstudio") or host in {"localhost", "127.0.0.1", "::1"}:
        return "lmstudio"
    return "openai-compatible"


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _nonnegative_number(value: Any) -> float | int | None:
    if isinstance(value, bool) or not isinstance(value, Real) or value < 0:
        return None
    return value


def normalize_provider_usage(document: dict[str, Any]) -> dict[str, Any] | None:
    """Normalize OpenAI-compatible usage while retaining provider cost details."""
    raw = document.get("usage")
    if not isinstance(raw, dict):
        return None

    aliases = {
        "prompt_tokens": ("prompt_tokens", "input_tokens"),
        "completion_tokens": ("completion_tokens", "output_tokens"),
        "total_tokens": ("total_tokens",),
    }
    usage: dict[str, Any] = {}
    for canonical, names in aliases.items():
        value = next((raw.get(name) for name in names if raw.get(name) is not None), None)
        parsed = _nonnegative_int(value)
        if parsed is not None:
            usage[canonical] = parsed

    if "total_tokens" not in usage and {"prompt_tokens", "completion_tokens"} <= usage.keys():
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]

    cost = _nonnegative_number(raw.get("cost"))
    if cost is not None:
        usage["cost_usd"] = cost

    completion_details = raw.get("completion_tokens_details")
    if isinstance(completion_details, dict):
        reasoning = _nonnegative_int(completion_details.get("reasoning_tokens"))
        if reasoning is not None:
            usage["reasoning_tokens"] = reasoning

    prompt_details = raw.get("prompt_tokens_details")
    if isinstance(prompt_details, dict):
        cached = _nonnegative_int(prompt_details.get("cached_tokens"))
        if cached is not None:
            usage["cached_tokens"] = cached
        cache_write = _nonnegative_int(prompt_details.get("cache_write_tokens"))
        if cache_write is not None:
            usage["cache_write_tokens"] = cache_write

    cost_details = raw.get("cost_details")
    if isinstance(cost_details, dict):
        upstream = _nonnegative_number(cost_details.get("upstream_inference_cost"))
        if upstream is not None:
            usage["cost_details"] = {"upstream_inference_cost": upstream}

    return usage or None


def generation_id(document: dict[str, Any]) -> str | None:
    value = document.get("id")
    return value if isinstance(value, str) and value.strip() else None


def _empty_ledger() -> dict[str, Any]:
    return {"schema_version": SCHEMA_VERSION, "calls": []}


def load_ledger(path: str | Path) -> dict[str, Any] | None:
    path = Path(path)
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return None
    if not isinstance(doc, dict) or not isinstance(doc.get("calls"), list):
        return None
    # Schema v1 is intentionally accepted; missing v2 fields are derived/fallback.
    if doc.get("schema_version") not in (1, SCHEMA_VERSION, None):
        return None
    return doc


def record_call(
    path: str | Path,
    operation: str,
    model: str,
    attempt: int,
    usage: dict[str, Any] | None,
    *,
    role: str | None = None,
    provider: str | None = None,
    duration_ms: int | None = None,
    logical_operation: str | None = None,
    call_kind: str = "model",
    error: Exception | str | None = None,
    generation_id_value: str | None = None,
) -> None:
    path = Path(path)
    doc = load_ledger(path) or _empty_ledger()
    calls = doc.setdefault("calls", [])
    row: dict[str, Any] = {
        "call_index": len(calls) + 1,
        "operation": operation,
        "logical_operation": logical_operation or operation,
        "call_kind": call_kind,
        "role": role,
        "provider": provider,
        "model": model,
        "attempt": attempt,
        "duration_ms": duration_ms,
        "usage": usage,
    }
    if generation_id_value:
        row["generation_id"] = generation_id_value
    if error:
        row["error"] = str(error)
    calls.append(row)
    doc["schema_version"] = SCHEMA_VERSION
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def _usage_totals(usages: list[dict[str, Any]]) -> dict[str, Any]:
    totals: dict[str, Any] = {
        key: sum(int(u.get(key, 0) or 0) for u in usages) for key in TOKEN_FIELDS
    }
    for key in ("reasoning_tokens", "cached_tokens", "cache_write_tokens"):
        values = [u.get(key) for u in usages if _nonnegative_int(u.get(key)) is not None]
        if values:
            totals[key] = sum(int(v) for v in values)
    return totals


def summarize(path: str | Path) -> dict[str, Any] | None:
    doc = load_ledger(path)
    if doc is None:
        return None
    calls = doc.get("calls", [])
    reported = [r.get("usage") for r in calls if isinstance(r.get("usage"), dict)]
    logical: list[str] = []
    for row in calls:
        op = row.get("logical_operation") or row.get("operation")
        if op and op not in logical:
            logical.append(op)

    def rows_for(op: str) -> list[dict[str, Any]]:
        return [r for r in calls if (r.get("logical_operation") or r.get("operation")) == op]

    by_operation: dict[str, Any] = {}
    for op in logical:
        rows = rows_for(op)
        usages = [r.get("usage") for r in rows if isinstance(r.get("usage"), dict)]
        costs = [u.get("cost_usd") for u in usages if _nonnegative_number(u.get("cost_usd")) is not None]
        model_rows = [r for r in rows if r.get("call_kind", "model") == "model"]
        by_operation[op] = {
            "physical_calls": len(rows),
            "retry_calls": max(0, len(model_rows) - 1),
            "syntax_repair_calls": sum(1 for r in rows if r.get("call_kind") == "syntax_repair"),
            "duration_ms": sum(int(r.get("duration_ms") or 0) for r in rows),
            "tokens": _usage_totals(usages),
            "cost": {
                "currency": "USD",
                "amount": sum(float(v) for v in costs) if costs else None,
                "reported_calls": len(costs),
                "unreported_calls": len(rows) - len(costs),
                "complete": bool(rows) and len(costs) == len(rows),
            },
        }

    cost_values = [u.get("cost_usd") for u in reported if _nonnegative_number(u.get("cost_usd")) is not None]
    providers = sorted({str(r.get("provider")) for r in calls if r.get("provider")})
    return {
        "schema_version": SCHEMA_VERSION,
        "logical_operations": len(logical),
        "physical_calls": len(calls),
        # Compatibility alias for older consumers of terraced-v6 summaries.
        "calls": len(calls),
        "retry_calls": sum(max(0, len([r for r in rows_for(op) if r.get("call_kind", "model") == "model"]) - 1) for op in logical),
        "syntax_repair_calls": sum(1 for r in calls if r.get("call_kind") == "syntax_repair"),
        "reported_calls": len(reported),
        "unreported_calls": len(calls) - len(reported),
        "duration_ms": sum(int(r.get("duration_ms") or 0) for r in calls),
        "providers": providers,
        "totals": _usage_totals(reported),
        "cost": {
            "currency": "USD",
            "amount": sum(float(v) for v in cost_values) if cost_values else None,
            "reported_calls": len(cost_values),
            "unreported_calls": len(calls) - len(cost_values),
            "complete": bool(calls) and len(cost_values) == len(calls),
        },
        "by_operation": by_operation,
    }


def format_status_lines(summary: dict[str, Any] | None) -> list[str]:
    """Format provider accounting consistently for CLI workflow status output."""
    if summary is None:
        return ["Token usage: unavailable (self handoff or no provider usage ledger)"]

    lines = [
        "Model execution: "
        f"{summary['logical_operations']} logical operation(s), "
        f"{summary['physical_calls']} provider call(s), "
        f"{summary['retry_calls']} retry call(s), "
        f"{summary['syntax_repair_calls']} syntax-repair call(s), "
        f"{summary['duration_ms']/1000:.2f}s provider runtime"
    ]
    if summary["reported_calls"]:
        t = summary["totals"]
        suffix = (
            f"; partial, {summary['unreported_calls']} attempt(s) unreported"
            if summary["unreported_calls"] else ""
        )
        lines.append(
            f"Token usage: prompt {t['prompt_tokens']:,}, completion {t['completion_tokens']:,}, "
            f"total {t['total_tokens']:,}{suffix}"
        )
    else:
        lines.append("Token usage: unavailable (provider did not report usage)")

    cost = summary.get("cost") or {}
    amount = cost.get("amount")
    if amount is not None:
        provider_label = "OpenRouter" if summary.get("providers") == ["openrouter"] else "Model"
        suffix = ""
        if not cost.get("complete"):
            suffix = f" (partial; {cost.get('unreported_calls', 0)} call(s) did not report cost)"
        lines.append(f"{provider_label} cost: US${float(amount):.6f}{suffix}")
    elif summary.get("providers") == ["openrouter"]:
        lines.append("OpenRouter cost: unavailable (provider did not report monetary usage)")
    return lines
