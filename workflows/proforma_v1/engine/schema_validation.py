"""Generic parse -> schema -> checks -> assembly validation pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

from workflows.proforma_v1.engine import assemblers, checks


class StructuredValidationError(ValueError):
    pass


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            line = key_node.start_mark.line + 1
            raise StructuredValidationError(f"malformed yaml: duplicate mapping key {key!r} at line {line}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def parse(raw: str, fmt: str) -> Any:
    try:
        if fmt == "json":
            return json.loads(raw)
        if fmt == "yaml":
            return yaml.load(raw, Loader=_UniqueKeyLoader)
        if fmt == "text":
            return raw
    except StructuredValidationError:
        raise
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise StructuredValidationError(f"malformed {fmt}: {exc}") from exc
    raise StructuredValidationError(f"unknown structured output format {fmt!r}")


def load_schema(path: Path) -> dict:
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(doc)
        return doc
    except (OSError, json.JSONDecodeError, Exception) as exc:
        if isinstance(exc, StructuredValidationError):
            raise
        raise StructuredValidationError(f"invalid JSON Schema {path}: {exc}") from exc


def validate_doc(doc: Any, schema: dict, *, label: str = "artifact") -> Any:
    errors = sorted(Draft202012Validator(schema).iter_errors(doc), key=lambda e: list(map(str, e.absolute_path)))
    if errors:
        first = errors[0]
        where = ".".join(str(p) for p in first.absolute_path) or "<root>"
        raise StructuredValidationError(f"{label} schema violation at {where}: {first.message}")
    return doc


def validate(
    raw: str,
    *,
    fmt: str,
    schema: dict | None = None,
    check_specs: list[dict] | tuple[dict, ...] = (),
    context: dict | None = None,
    assembly: dict | None = None,
    final_schema: dict | None = None,
) -> Any:
    doc = parse(raw, fmt)
    if schema is not None:
        validate_doc(doc, schema, label="model output")
    checks.apply(doc, check_specs, context=context or {})
    if assembly:
        name = assembly.get("type", "passthrough")
        doc = assemblers.assemble(name, doc, spec=assembly, context=context or {})
    if final_schema is not None:
        validate_doc(doc, final_schema, label="assembled artifact")
    return doc
