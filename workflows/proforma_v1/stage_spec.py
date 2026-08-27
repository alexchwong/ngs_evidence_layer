"""Load and validate model-stage contracts used by the Phase 2 workflow engine.

Stage YAML describes a model artifact contract: prompt, output schema, buckets,
relational rules, transforms, retries and reportability. Logical ordering and
dependencies no longer live here or in ``step.py``; they are compiled from the
canonical ``workflow.yaml``.

Every referenced rule/transform remains allow-listed so configuration cannot
become an arbitrary-code execution mechanism.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

HERE = Path(__file__).resolve().parent
STAGE_ROOT = HERE / "stages"
META_SCHEMA = STAGE_ROOT / "_stage.schema.json"

STAGE_TYPES = ("model", "domain_proforma", "batch", "compound")
TRANSFORMS = ("consolidate_parallel_variant_rows", "derive_diagnostic_cmcs", "finalize_diagnosis", "finalize_evidence", "identity", "load_corpus", "report_blocks")


class StageSpecError(ValueError):
    """A stage asset is malformed or references something unregistered."""


@dataclass(frozen=True)
class StageSpec:
    stage: str
    type: str
    role: str | None
    prompt: str | None
    path: Path
    doc: dict

    # --- convenience views used by the domain contract and the runners -------
    @property
    def label(self) -> str:
        return str(self.doc.get("label") or self.stage)

    @property
    def buckets(self) -> tuple[str, ...]:
        return tuple(self.doc.get("buckets") or ())

    @property
    def extra_keys(self) -> tuple[str, ...]:
        return tuple(self.doc.get("extra_keys") or ())

    @property
    def therapy_buckets(self) -> tuple[str, ...]:
        return tuple(self.doc.get("therapy_buckets") or ())

    @property
    def solitary_buckets(self) -> tuple[str, ...]:
        return tuple(self.doc.get("solitary_buckets") or ())

    @property
    def multi_row(self) -> bool:
        return bool(self.doc.get("multi_row"))

    @property
    def guidance(self) -> tuple[str, ...]:
        return tuple(self.doc.get("guidance") or ())

    @property
    def rules(self) -> tuple[dict, ...]:
        return tuple(self.doc.get("rules") or ())

    @property
    def transforms(self) -> tuple[str, ...]:
        return tuple(self.doc.get("transforms") or ())

    @property
    def output_format(self) -> str:
        return str(self.doc["output"]["format"])

    @property
    def schema_name(self) -> str:
        return str(self.doc["output"]["schema"])

    @property
    def output_path(self) -> str | None:
        return self.doc["output"].get("path")

    @property
    def reportability(self) -> dict:
        return dict(self.doc.get("reportability") or {})

    def retries(self, kind: str, default: int) -> int:
        return int((self.doc.get("retries") or {}).get(kind, default))

    @property
    def inputs(self) -> dict:
        return dict(self.doc.get("inputs") or {})


@lru_cache(maxsize=1)
def _meta_validator() -> Draft202012Validator:
    schema = json.loads(META_SCHEMA.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def _validate_asset(doc, path: Path) -> None:
    errors = sorted(_meta_validator().iter_errors(doc), key=lambda e: list(map(str, e.absolute_path)))
    if errors:
        first = errors[0]
        where = ".".join(str(p) for p in first.absolute_path) or "<root>"
        raise StageSpecError(f"{path.name}: invalid stage asset at {where}: {first.message}")
    if doc["type"] not in STAGE_TYPES:
        raise StageSpecError(f"{path.name}: unknown stage type {doc['type']!r}")
    for transform in doc.get("transforms") or []:
        if transform not in TRANSFORMS:
            raise StageSpecError(
                f"{path.name}: unknown transform {transform!r}; registered: {list(TRANSFORMS)}"
            )
    known_buckets = set(doc.get("buckets") or ())
    for key in ("therapy_buckets", "solitary_buckets"):
        unknown = sorted(set(doc.get(key) or ()) - known_buckets)
        if unknown:
            raise StageSpecError(f"{path.name}: {key} names non-existent bucket(s) {unknown}")
    for bucket in doc.get("reportability") or {}:
        if known_buckets and bucket not in known_buckets and bucket not in (doc.get("extra_keys") or ()):
            raise StageSpecError(
                f"{path.name}: reportability names {bucket!r}, which is not a bucket or extra key"
            )


@lru_cache(maxsize=1)
def _load_all() -> dict[str, StageSpec]:
    # Imported here to avoid a circular import at module load: the rule registry
    # imports issue builders, which do not depend on stage specs.
    from workflows.proforma_v1 import rules as rule_registry

    out: dict[str, StageSpec] = {}
    for path in sorted(STAGE_ROOT.glob("*.yaml")):
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(doc, dict):
            raise StageSpecError(f"{path.name}: stage asset must be a mapping")
        _validate_asset(doc, path)
        for rule in doc.get("rules") or []:
            if rule["rule"] not in rule_registry.REGISTRY:
                raise StageSpecError(
                    f"{path.name}: unknown rule {rule['rule']!r}; "
                    f"registered: {sorted(rule_registry.REGISTRY)}"
                )
        spec = StageSpec(
            stage=doc["stage"],
            type=doc["type"],
            role=doc.get("role"),
            prompt=doc.get("prompt"),
            path=path,
            doc=doc,
        )
        if spec.stage in out:
            raise StageSpecError(f"duplicate stage id {spec.stage!r}")
        if spec.stage != path.stem:
            raise StageSpecError(f"{path.name}: declares stage {spec.stage!r}; file name must match")
        out[spec.stage] = spec
    return out


def names() -> tuple[str, ...]:
    return tuple(sorted(_load_all()))


def load(stage: str) -> StageSpec:
    specs = _load_all()
    if stage not in specs:
        raise StageSpecError(f"unknown stage {stage!r}; choose one of: {', '.join(sorted(specs))}")
    return specs[stage]


def domains() -> tuple[str, ...]:
    """Stage ids that are PTBG owner proformas, in asset order."""
    return tuple(s for s in names() if _load_all()[s].type == "domain_proforma")


def check_all() -> list[str]:
    """Load every asset, returning one description line per stage."""
    _load_all.cache_clear()
    lines = []
    for name in names():
        spec = load(name)
        detail = f"  {name}: type={spec.type} schema={spec.schema_name} rules={len(spec.rules)}"
        if spec.buckets:
            detail += f" buckets={list(spec.buckets)}"
        lines.append(detail)
    return lines
