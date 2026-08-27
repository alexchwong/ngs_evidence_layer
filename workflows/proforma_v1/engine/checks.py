"""Generic cross-artifact deterministic checks plus safe custom registry."""
from __future__ import annotations

from typing import Any, Callable


class CheckFailure(ValueError):
    def __init__(self, rule: str, path: str, problem: str):
        super().__init__(f"{rule} at {path}: {problem}")
        self.rule = rule
        self.path = path
        self.problem = problem


def _path(value: Any, path: str) -> Any:
    cur = value
    if not path:
        return cur
    for part in path.split("."):
        if part.endswith("[]"):
            key = part[:-2]
            cur = cur.get(key, []) if isinstance(cur, dict) else []
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        else:
            return None
    return cur


def _source(context: dict, ref: str) -> Any:
    if ref in context:
        return context[ref]
    cur: Any = context
    for part in ref.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def _values(doc: Any, path: str) -> list[Any]:
    if "[]" not in path:
        value = _path(doc, path)
        return value if isinstance(value, list) else [value]
    left, right = path.split("[]", 1)
    rows = _path(doc, left.rstrip(".")) or []
    suffix = right.lstrip(".")
    return [_path(row, suffix) if suffix else row for row in rows]


def equals(doc, context, spec):
    actual = _path(doc, spec.get("path", ""))
    if actual != spec.get("value"):
        raise CheckFailure("equals", spec.get("path", ""), f"expected {spec.get('value')!r}; got {actual!r}")


def equals_source(doc, context, spec):
    actual = _path(doc, spec.get("path", "")); expected = _source(context, spec["source"])
    if actual != expected:
        raise CheckFailure("equals_source", spec.get("path", ""), f"does not match {spec['source']!r}")


def subset(doc, context, spec):
    actual = set(_values(doc, spec.get("path", "")) if "[]" in spec.get("path", "") else (_path(doc, spec.get("path", "")) or []))
    allowed = set(_source(context, spec["source"]) or [])
    unknown = actual - allowed
    if unknown:
        raise CheckFailure("subset", spec.get("path", ""), f"unknown value(s): {sorted(map(str, unknown))}")


def member_of(doc, context, spec):
    actual = _path(doc, spec.get("path", "")); allowed = set(_source(context, spec["source"]) or [])
    if actual not in allowed:
        raise CheckFailure("member_of", spec.get("path", ""), f"{actual!r} is not in {spec['source']!r}")


def unique(doc, context, spec):
    values = _values(doc, spec.get("path", "")); seen = set(); dup = []
    for value in values:
        marker = repr(value)
        if marker in seen: dup.append(value)
        seen.add(marker)
    if dup:
        raise CheckFailure("unique", spec.get("path", ""), f"duplicate value(s): {dup}")


def sequential_ids(doc, context, spec):
    rows = _path(doc, spec.get("path", "")) or []
    field = spec.get("field", "id"); prefix = spec.get("prefix", "")
    width = int(spec.get("width", 2))
    expected = [f"{prefix}{i:0{width}d}" for i in range(1, len(rows) + 1)]
    actual = [row.get(field) if isinstance(row, dict) else None for row in rows]
    if actual != expected:
        raise CheckFailure("sequential_ids", spec.get("path", ""), f"expected {expected}; got {actual}")


def one_row_per(doc, context, spec):
    rows = _path(doc, spec.get("path", "")) or []
    key = spec.get("key", "id")
    actual = [row.get(key) for row in rows if isinstance(row, dict)]
    expected = list(_source(context, spec["source"]) or [])
    if actual != expected:
        raise CheckFailure("one_row_per", spec.get("path", ""), f"expected exact row keys {expected}; got {actual}")


def _when(row: dict, when: dict) -> bool:
    value = _path(row, when.get("path", ""))
    if "equals" in when: return value == when["equals"]
    if "in" in when: return value in when["in"]
    if "not_in" in when: return value not in when["not_in"]
    return bool(value)


def required_when(doc, context, spec):
    path = spec.get("path", "")
    if "[]." in path:
        rows_path, field = path.split("[].", 1)
        for i, row in enumerate(_path(doc, rows_path) or []):
            if isinstance(row, dict) and _when(row, spec.get("when") or {}) and row.get(field) in (None, ""):
                raise CheckFailure("required_when", f"{rows_path}[{i}].{field}", "value is required by condition")
    elif _when(doc, spec.get("when") or {}) and _path(doc, path) in (None, ""):
        raise CheckFailure("required_when", path, "value is required by condition")


def null_when(doc, context, spec):
    path = spec.get("path", "")
    if "[]." in path:
        rows_path, field = path.split("[].", 1)
        for i, row in enumerate(_path(doc, rows_path) or []):
            if isinstance(row, dict) and _when(row, spec.get("when") or {}) and row.get(field) is not None:
                raise CheckFailure("null_when", f"{rows_path}[{i}].{field}", "value must be null by condition")
    elif _when(doc, spec.get("when") or {}) and _path(doc, path) is not None:
        raise CheckFailure("null_when", path, "value must be null by condition")


def ordered_by_source(doc, context, spec):
    actual = _values(doc, spec.get("path", "")); expected = list(_source(context, spec["source"]) or [])
    if actual != expected:
        raise CheckFailure("ordered_by_source", spec.get("path", ""), f"expected {expected}; got {actual}")


def field_matches_source(doc, context, spec):
    rows = _path(doc, spec.get("rows", "")) or []
    source = _source(context, spec["source"]) or []
    if isinstance(source, dict): source_rows = list(source.values())
    else: source_rows = list(source)
    source_map = {str(row[spec["source_key"]]): row for row in source_rows}
    for i, row in enumerate(rows):
        key = str(row.get(spec["row_key"]))
        expected = _path(source_map.get(key, {}), spec["source_path"])
        actual = _path(row, spec.get("path", ""))
        if actual != expected:
            raise CheckFailure("field_matches_source", f"{spec.get('rows')}[{i}].{spec.get('path')}", f"expected {expected!r}; got {actual!r}")


CUSTOM_REGISTRY: dict[str, Callable] = {}


def register_custom(name: str, fn: Callable) -> None:
    """Register a developer-owned deterministic check handler."""
    if not name or not callable(fn):
        raise ValueError("custom check registration requires a name and callable")
    CUSTOM_REGISTRY[name] = fn


def custom(doc, context, spec):
    handler = spec.get("handler")
    fn = CUSTOM_REGISTRY.get(handler)
    if fn is None:
        raise CheckFailure("custom", spec.get("path", "<workflow>"), f"unknown custom check handler {handler!r}")
    result = fn(doc, context, spec.get("params") or {})
    if result:
        raise CheckFailure("custom", spec.get("path", "<workflow>"), str(result))


REGISTRY = {
    "custom": custom,
    "equals": equals,
    "equals_source": equals_source,
    "subset": subset,
    "member_of": member_of,
    "unique": unique,
    "sequential_ids": sequential_ids,
    "one_row_per": one_row_per,
    "required_when": required_when,
    "null_when": null_when,
    "ordered_by_source": ordered_by_source,
    "field_matches_source": field_matches_source,
}

# Existing stage-rule names remain compile-time allow-listed. Their concrete
# execution stays in rules.py so Phase 1 validation feedback remains byte-stable.
from workflows.proforma_v1 import rules as _stage_rules
for _name in _stage_rules.REGISTRY:
    REGISTRY.setdefault(_name, None)


def apply(doc: Any, checks: list[dict] | tuple[dict, ...], *, context: dict | None = None) -> Any:
    context = context or {}
    for spec in checks or ():
        name = spec.get("rule")
        fn = REGISTRY.get(name)
        if name not in REGISTRY:
            raise CheckFailure(str(name), spec.get("path", "<workflow>"), "unknown deterministic check")
        if fn is not None:
            fn(doc, context, spec)
    return doc
