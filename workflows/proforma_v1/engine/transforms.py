"""Allow-listed deterministic transform extension point."""
from __future__ import annotations

from typing import Any


class TransformError(ValueError):
    pass


def identity(value: Any, context: dict, params: dict) -> Any:
    return value


def derive_diagnostic_cmcs(value: Any, context: dict, params: dict) -> Any:
    from workflows.proforma_v1 import runtime
    return runtime.derive_cmcs(value or {})


def delegated(value: Any, context: dict, params: dict) -> Any:
    """Marker for transforms still implemented by the v6-compatible handler."""
    return value


REGISTRY = {
    "identity": identity,
    "load_corpus": delegated,
    "finalize_diagnosis": delegated,
    "finalize_evidence": delegated,
    "report_blocks": delegated,
    "consolidate_parallel_variant_rows": delegated,
    "derive_diagnostic_cmcs": derive_diagnostic_cmcs,
}


def apply(name: str, value: Any, *, context: dict | None = None, params: dict | None = None) -> Any:
    if name not in REGISTRY:
        raise TransformError(f"unknown transform {name!r}; registered: {sorted(REGISTRY)}")
    return REGISTRY[name](value, context or {}, params or {})
