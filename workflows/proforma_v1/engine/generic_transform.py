"""Generic declarative deterministic-transform execution.

This adapter is intentionally opt-in. Existing workflows continue to use their
registered provider/self handlers. ``reasoning.yaml`` uses the special
``generic_transform`` handler name so new deterministic reasoning stages can be
implemented without adding workflow-specific branches to ``step.py`` or
``self.py``.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from workflows.proforma_v1.engine import artifacts as workflow_artifacts
from workflows.proforma_v1.engine import transforms


def _payload(context) -> dict[str, Any]:
    data = dict(getattr(context, "data", {}) or {})
    data["__work__"] = Path(context.work)
    data["__workflow_context__"] = context
    return data


def _write(path: Path, value: Any, fmt: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        text = json.dumps(value, indent=2, ensure_ascii=False) + "\n"
    elif fmt == "yaml":
        text = yaml.safe_dump(value, sort_keys=False, allow_unicode=True, width=110)
    else:
        text = str(value)
        if not text.endswith("\n"):
            text += "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def execute(step, context) -> dict[str, Any]:
    if not step.transform:
        raise RuntimeError(f"generic transform step {step.id!r} has no transform")
    params = dict((step.execution or {}).get("params") or {})
    params["step_id"] = step.id
    value = transforms.apply(step.transform, None, context=_payload(context), params=params)
    artifact = (step.output or {}).get("artifact")
    if artifact:
        context.put(artifact, value)
        path = workflow_artifacts.generic_output_path(context.work, step, create=True)
        _write(path, value, str((step.output or {}).get("format") or "yaml").lower())
    return {"status": "complete", "artifact": value}


def hydrate(step_id: str, context) -> bool:
    workflow = context.get("workflow")
    if workflow is None:
        return False
    try:
        step = workflow.step(step_id)
    except KeyError:
        return False
    if (step.execution or {}).get(f"{context.executor}_handler") != "generic_transform":
        return False
    path = workflow_artifacts.generic_output_path(context.work, step, create=False)
    if not path.is_file():
        return False
    fmt = str((step.output or {}).get("format") or "yaml").lower()
    raw = path.read_text(encoding="utf-8")
    value = json.loads(raw) if fmt == "json" else yaml.safe_load(raw) if fmt == "yaml" else raw
    artifact = (step.output or {}).get("artifact")
    if artifact:
        context.put(artifact, value)
    # Reasoning workflow keeps legacy report handlers as thin presentation
    # adapters. Restore their established context aliases on resume as well as
    # during fresh deterministic execution. Default workflow transforms never
    # use these reasoning-specific transform names.
    if step.transform == "reasoning_report_blocks":
        context.put("blocks", value)
    elif step.transform == "reasoning_finalize_atomic_evidence":
        context.put("supported", value)
    return True
