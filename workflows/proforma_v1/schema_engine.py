"""Adapt `jsonschema` structural errors onto the proforma-v1 feedback vocabulary.

Structure is expressed in real JSON Schema (Draft 2020-12). `jsonschema>=4.0` is
already a declared dependency of this repository and is already used by
`scripts/phase_validation/` — there is no reason to hand-roll a resolver for
`$ref`, `$defs`, `oneOf` and `additionalProperties`.

What this module does *not* do is pass `jsonschema`'s own messages through.
Those are written for developers, and for `enum` they embed the entire
vocabulary — which is precisely the failure this workflow removed in Phase 1.
Every error is instead mapped onto an `issues.py` builder so a model sees the
same wording it would have seen from a hand-written validator.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator

from scripts.core.validated_model_task import ValidationIssue
from workflows.proforma_v1 import issues as iss

SCHEMA_ROOT = Path(__file__).resolve().parent / "schemas"


@lru_cache(maxsize=None)
def load(name: str) -> dict:
    path = name if Path(name).is_absolute() else SCHEMA_ROOT / Path(name).name
    with open(path, encoding="utf-8") as handle:
        schema = json.load(handle)
    Draft202012Validator.check_schema(schema)
    return schema


def json_path(parts) -> str:
    out = ""
    for part in parts:
        out += f"[{part}]" if isinstance(part, int) else (f".{part}" if out else str(part))
    return out


def _required_issue(err, path) -> list[ValidationIssue]:
    expected = sorted(err.schema.get("properties", {}) or [])
    return iss.exact_keys(err.instance, set(expected), path) if expected else [
        ValidationIssue(
            path,
            f"missing required key(s) {sorted(err.validator_value)}",
            f"return every required key: {sorted(err.validator_value)}",
            repair_class="content",
            received=str(sorted(err.instance)) if isinstance(err.instance, dict) else iss.preview(err.instance),
        )
    ]


def _type_issue(err, path) -> list[ValidationIssue]:
    wanted = err.validator_value
    wanted = wanted if isinstance(wanted, str) else "/".join(wanted)
    if wanted == "string":
        return iss.text_field(err.instance, path)
    if wanted == "boolean":
        return iss.bool_field(err.instance, path)
    # A scalar that should have been a one-item list, or a single object that
    # should have been wrapped, is reserialization rather than a content defect.
    reserializable = (wanted == "array" and not isinstance(err.instance, (list, type(None)))) or (
        wanted == "object" and isinstance(err.instance, list) and len(err.instance) == 1
    )
    return [
        ValidationIssue(
            path,
            f"expected {wanted}; received {iss.type_name(err.instance)}",
            "reserialize the existing value with the correct structure, without changing its content"
            if reserializable
            else f"supply a {wanted} value",
            repair_class="serialization" if reserializable else "content",
            received=iss.preview(err.instance),
            expected=wanted,
        )
    ]


def _combinator_issue(err, path) -> list[ValidationIssue]:
    """Collapse oneOf/anyOf rather than fanning out one issue per branch."""
    branches = []
    for sub in err.validator_value or []:
        if sub.get("type") == "null":
            branches.append("null")
        elif "$ref" in sub:
            branches.append(str(sub["$ref"]).rsplit("/", 1)[-1])
        else:
            branches.append(sub.get("type", "value"))
    return [
        ValidationIssue(
            path,
            f"does not match any allowed form ({', '.join(branches)})",
            f"use one of: {', '.join(branches)}",
            repair_class="content",
            received=iss.preview(err.instance),
            expected=" | ".join(branches),
        )
    ]


def issues_from_schema(doc, schema, *, context: str) -> list[ValidationIssue]:
    """Map structural schema errors onto ValidationIssue, deterministically ordered."""
    validator = Draft202012Validator(schema)
    out: list[ValidationIssue] = []
    seen: set[tuple] = set()
    for err in sorted(validator.iter_errors(doc), key=lambda e: (list(map(str, e.absolute_path)), e.validator)):
        path = json_path(err.absolute_path) or context
        key = (path, err.validator)
        if key in seen:
            continue
        seen.add(key)
        kind = err.validator
        if kind == "required":
            out += _required_issue(err, path)
        elif kind == "additionalProperties":
            expected = sorted(err.schema.get("properties", {}) or [])
            out += iss.exact_keys(err.instance, set(expected), path)
        elif kind == "enum":
            out += iss.enum_field(err.instance, err.validator_value, path, label="value")
        elif kind == "type":
            out += _type_issue(err, path)
        elif kind in {"oneOf", "anyOf"}:
            out += _combinator_issue(err, path)
        elif kind == "minItems":
            out += [
                ValidationIssue(
                    path,
                    f"needs at least {err.validator_value} item(s); received {len(err.instance or [])}",
                    f"supply at least {err.validator_value} item(s)",
                    repair_class="content",
                    received=iss.preview(err.instance),
                )
            ]
        elif kind in {"minLength", "pattern"}:
            out += iss.text_field(err.instance, path)
        else:
            out += [
                ValidationIssue(
                    path,
                    f"does not satisfy the {kind} constraint",
                    "correct the value to satisfy the declared output contract",
                    repair_class="content",
                    received=iss.preview(err.instance),
                    expected=iss.preview(err.validator_value),
                )
            ]
    return out
