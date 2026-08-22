"""Scheduler registry for terraced-v3."""
from __future__ import annotations

from importlib import import_module

SCHEDULER_MODULES = {
    "domain": "workflows.terraced_v3.schedulers.domain",
    "evidence-first": "workflows.terraced_v3.schedulers.evidence_first",
    "variant-centric": "workflows.terraced_v3.schedulers.variant_centric",
    "global-ledger": "workflows.terraced_v3.schedulers.global_ledger",
    "adaptive-microtask": "workflows.terraced_v3.schedulers.adaptive_microtask",
}


def names() -> tuple[str, ...]:
    return tuple(SCHEDULER_MODULES)


def load(name: str):
    module_name = SCHEDULER_MODULES.get(name)
    if module_name is None:
        raise ValueError(f"unknown terraced-v3 scheduler {name!r}; choose one of: {', '.join(names())}")
    module = import_module(module_name)
    if getattr(module, "SCHEDULER_ID", None) != name or not callable(getattr(module, "run", None)):
        raise ValueError(f"scheduler module {module_name} does not implement the terraced-v3 scheduler API")
    return module


def descriptions() -> dict[str, str]:
    return {name: str(getattr(load(name), "DESCRIPTION", "")) for name in names()}
