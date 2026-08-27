"""Small deterministic form-assembly registry."""
from __future__ import annotations

from copy import deepcopy
from typing import Any


class AssemblyError(ValueError):
    pass


def passthrough(model_output: Any, *, spec: dict, context: dict) -> Any:
    return deepcopy(model_output)


def object_merge(model_output: Any, *, spec: dict, context: dict) -> dict:
    base = deepcopy(context.get(spec.get("source", ""), {})) if spec.get("source") else {}
    if not isinstance(base, dict) or not isinstance(model_output, dict):
        raise AssemblyError("object_merge requires mapping source and model output")
    allowed = spec.get("model_fields")
    incoming = model_output if not allowed else {k: model_output[k] for k in allowed if k in model_output}
    unknown = set(model_output) - set(allowed or model_output)
    if unknown:
        raise AssemblyError(f"model output contains non-owned field(s): {sorted(unknown)}")
    base.update(deepcopy(incoming))
    return base


def keyed_rows(model_output: Any, *, spec: dict, context: dict) -> dict:
    source = context.get(spec.get("source"))
    if isinstance(source, dict):
        source_rows = list(source.values())
    elif isinstance(source, list):
        source_rows = source
    else:
        raise AssemblyError("keyed_rows source must be a list or mapping")
    answers_path = spec.get("answers_path", "answers")
    answers = model_output.get(answers_path) if isinstance(model_output, dict) else None
    if not isinstance(answers, dict):
        raise AssemblyError(f"keyed_rows requires mapping at {answers_path!r}")
    source_key = spec.get("source_key", "id")
    known = {str(row[source_key]) for row in source_rows}
    extra = sorted(set(map(str, answers)) - known)
    if extra:
        raise AssemblyError(f"unknown answer ID(s): {extra}")
    if not spec.get("allow_missing", False):
        missing = sorted(known - set(map(str, answers)))
        if missing:
            raise AssemblyError(f"missing answer ID(s): {missing}")
    deterministic = spec.get("deterministic_fields") or {}
    model_fields = tuple(spec.get("model_fields") or ())
    rows = []
    for row in source_rows:
        key = str(row[source_key])
        answer = answers.get(key, {})
        if not isinstance(answer, dict):
            raise AssemblyError(f"answer {key!r} must be a mapping")
        unknown = sorted(set(answer) - set(model_fields)) if model_fields else []
        if unknown:
            raise AssemblyError(f"answer {key!r} contains non-owned field(s): {unknown}")
        built = {}
        for dest, rule in deterministic.items():
            built[dest] = deepcopy(row[rule["from_row"]])
        for field in model_fields:
            if field in answer:
                built[field] = deepcopy(answer[field])
        rows.append(built)
    return {spec.get("output_path", "classification"): rows}


def list_rows(model_output: Any, *, spec: dict, context: dict) -> list:
    if not isinstance(model_output, list):
        raise AssemblyError("list_rows requires a list model output")
    return deepcopy(model_output)


REGISTRY = {
    "passthrough": passthrough,
    "object_merge": object_merge,
    "keyed_rows": keyed_rows,
    "list_rows": list_rows,
}


def assemble(name: str, model_output: Any, *, spec: dict | None = None, context: dict | None = None) -> Any:
    if name not in REGISTRY:
        raise AssemblyError(f"unknown assembler {name!r}; registered: {sorted(REGISTRY)}")
    return REGISTRY[name](model_output, spec=spec or {}, context=context or {})
