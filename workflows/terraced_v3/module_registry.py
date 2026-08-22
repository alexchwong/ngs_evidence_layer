"""Core/adaptor module asset discovery for terraced-v3 pipelines."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml

from workflows.terraced_v3 import contract_registry

HERE = Path(__file__).resolve().parent
CORE_ROOT = HERE / "modules" / "core"
ADAPTER_ROOT = HERE / "adapters"


@dataclass(frozen=True)
class ModuleSpec:
    module_id: str
    kind: str
    handler: str
    description: str
    path: Path
    inputs: dict[str, str]
    outputs: dict[str, str]


def _load_asset(path: Path, *, kind: str) -> ModuleSpec:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot read module asset {path}: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("module"), dict):
        raise ValueError(f"module asset requires module mapping: {path}")
    meta = doc["module"]
    mid = meta.get("id"); handler = meta.get("handler")
    if not isinstance(mid, str) or not mid:
        raise ValueError(f"module asset requires non-empty module.id: {path}")
    if not isinstance(handler, str) or not handler:
        raise ValueError(f"module asset {mid!r} requires non-empty handler")
    inputs: dict[str, str] = {}; outputs: dict[str, str] = {}
    for label, target in (("inputs", inputs), ("outputs", outputs)):
        rows = doc.get(label) or {}
        if not isinstance(rows, dict):
            raise ValueError(f"module {mid!r} {label} must be a mapping")
        for name, rule in rows.items():
            if not isinstance(name, str) or not name:
                raise ValueError(f"module {mid!r} has invalid {label} name")
            if not isinstance(rule, dict) or not isinstance(rule.get("contract"), str):
                raise ValueError(f"module {mid!r} {label}.{name} must declare contract")
            ref = rule["contract"]
            contract_registry.load(ref, base=path.parent)
            target[name] = ref
    return ModuleSpec(mid, kind, handler, str(meta.get("description") or ""), path, inputs, outputs)


def core_names() -> tuple[str, ...]:
    names=[]
    if CORE_ROOT.is_dir():
        for path in CORE_ROOT.glob("*.yaml"):
            names.append(_load_asset(path, kind="core").module_id)
    return tuple(sorted(names))


def load_core(module_id: str) -> ModuleSpec:
    for path in CORE_ROOT.glob("*.yaml") if CORE_ROOT.is_dir() else []:
        spec=_load_asset(path, kind="core")
        if spec.module_id == module_id:
            return spec
    raise ValueError(f"unknown core pipeline module {module_id!r}; choose one of: {', '.join(core_names())}")


def adapter_names() -> tuple[str, ...]:
    names=[]
    if ADAPTER_ROOT.is_dir():
        for path in ADAPTER_ROOT.glob("*.yaml"):
            names.append(_load_asset(path, kind="adapter").module_id)
    return tuple(sorted(names))


def load_adapter(module_id: str) -> ModuleSpec:
    for path in ADAPTER_ROOT.glob("*.yaml") if ADAPTER_ROOT.is_dir() else []:
        spec=_load_asset(path, kind="adapter")
        if spec.module_id == module_id:
            return spec
    raise ValueError(f"unknown adapter module {module_id!r}; choose one of: {', '.join(adapter_names())}")
