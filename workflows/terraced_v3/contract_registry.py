"""Inspect and resolve terraced-v3 Markdown data contracts.

Contracts are Markdown files with small YAML frontmatter.  The frontmatter is
machine-readable enough for pipeline compatibility checks; the Markdown body
is the human/model-facing specification and may contain an example structured
artifact.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import re
import yaml

HERE = Path(__file__).resolve().parent
CORE_ROOT = HERE / "contracts" / "core"
_FRONT = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?(.*)\Z", re.S)


@dataclass(frozen=True)
class Contract:
    ref: str
    path: Path
    semantic_type: str
    format: str
    provides: tuple[str, ...]
    requires: tuple[str, ...]
    runtime_invariants: tuple[str, ...]
    validator: str | None
    body: str
    meta: dict[str, Any]

    @property
    def model_text(self) -> str:
        return self.body.strip()


def _core_path(ref: str) -> Path:
    if not ref.startswith("core."):
        raise ValueError(f"not a core contract reference: {ref!r}")
    rel = Path(*ref[len("core."):].split("."))
    return CORE_ROOT / rel.with_suffix(".md")


def resolve_path(ref: str, *, base: Path | None = None) -> Path:
    if ref.startswith("core."):
        return _core_path(ref)
    if ref.startswith("local."):
        if base is None:
            raise ValueError(f"local contract {ref!r} requires a scheduler/module base directory")
        rel = Path(*ref[len("local."):].split("."))
        return base / "contracts" / rel.with_suffix(".md")
    path = Path(ref)
    if not path.is_absolute():
        if base is None:
            raise ValueError(f"relative contract path {ref!r} requires a base directory")
        path = base / path
    return path.resolve()


def load(ref: str, *, base: Path | None = None) -> Contract:
    path = resolve_path(ref, base=base)
    if not path.is_file():
        raise ValueError(f"contract {ref!r} not found: {path}")
    text = path.read_text(encoding="utf-8")
    match = _FRONT.match(text)
    if not match:
        raise ValueError(f"contract must begin with YAML frontmatter delimited by ---: {path}")
    try:
        meta = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid contract frontmatter {path}: {exc}") from exc
    if not isinstance(meta, dict):
        raise ValueError(f"contract frontmatter must be a mapping: {path}")
    cid = meta.get("id")
    if not isinstance(cid, str) or not cid:
        raise ValueError(f"contract frontmatter requires non-empty id: {path}")
    semantic_type = meta.get("semantic_type")
    if not isinstance(semantic_type, str) or not semantic_type:
        raise ValueError(f"contract {cid!r} requires semantic_type")
    fmt = meta.get("format")
    if fmt not in {"yaml", "json", "markdown", "text", "service"}:
        raise ValueError(f"contract {cid!r} has unsupported format {fmt!r}")
    provides = meta.get("provides") or []
    requires = meta.get("requires") or []
    invariants = meta.get("runtime_invariants") or []
    for name, value in (("provides", provides), ("requires", requires), ("runtime_invariants", invariants)):
        if not isinstance(value, list) or any(not isinstance(v, str) or not v for v in value):
            raise ValueError(f"contract {cid!r} {name} must be a list of non-empty strings")
    validator = meta.get("validator")
    if validator is not None and (not isinstance(validator, str) or not validator):
        raise ValueError(f"contract {cid!r} validator must be a non-empty string or null")
    return Contract(
        ref=ref, path=path, semantic_type=semantic_type, format=fmt,
        provides=tuple(provides), requires=tuple(requires),
        runtime_invariants=tuple(invariants), validator=validator,
        body=match.group(2), meta=meta,
    )


def compatibility(producer: Contract, consumer: Contract) -> list[str]:
    """Return human-readable incompatibilities between two contracts."""
    issues: list[str] = []
    accepted = consumer.meta.get("accepts_semantic_types") or [consumer.semantic_type]
    if producer.semantic_type not in accepted and "*" not in accepted:
        issues.append(
            f"semantic type mismatch: upstream provides {producer.semantic_type!r}, "
            f"downstream expects one of {accepted!r}"
        )
    accepted_formats = consumer.meta.get("accepts_formats") or [consumer.format]
    if producer.format not in accepted_formats and "*" not in accepted_formats:
        issues.append(
            f"format mismatch: upstream provides {producer.format!r}, downstream accepts {accepted_formats!r}"
        )
    available = set(producer.provides)
    def covered(required: str) -> bool:
        if "*" in available or required in available:
            return True
        prefix = required + "."
        # Declaring child fields proves that the required parent/container exists.
        return any(field.startswith(prefix) for field in available)
    missing = [field for field in consumer.requires if not covered(field)]
    if missing:
        issues.append("missing required fields: " + ", ".join(missing))
    return issues


def core_refs() -> tuple[str, ...]:
    refs: list[str] = []
    if CORE_ROOT.is_dir():
        for path in CORE_ROOT.rglob("*.md"):
            rel = path.relative_to(CORE_ROOT).with_suffix("")
            refs.append("core." + ".".join(rel.parts))
    return tuple(sorted(refs))


def describe(contract: Contract) -> list[str]:
    lines = [
        f"contract: {contract.meta['id']}",
        f"file: {contract.path}",
        f"semantic_type: {contract.semantic_type}",
        f"format: {contract.format}",
    ]
    if contract.provides:
        lines.append("provides: " + ", ".join(contract.provides))
    if contract.requires:
        lines.append("requires: " + ", ".join(contract.requires))
    if contract.validator:
        lines.append(f"validator: {contract.validator}")
    if contract.runtime_invariants:
        lines.append("runtime_invariants: " + ", ".join(contract.runtime_invariants))
    return lines
