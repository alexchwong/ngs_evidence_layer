"""Declarative workflow progress planning and live run-state recording."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

SCHEMA_VERSION = 1
FINAL_STATES = {"completed", "skipped"}
VALID_STATES = {"pending", "running", "completed", "skipped", "failed"}


class ProgressPlanError(ValueError):
    """Raised when workflow progress presentation metadata is invalid."""


def _humanize(step_id: str) -> str:
    return step_id.replace("_", " ").replace(".", " · ").strip().title()


def progress_definition_path(workflow) -> Path:
    source = Path(workflow.source)
    return source.with_name(f"{source.stem}.progress.yaml")


def _fallback_plan(workflow) -> dict[str, Any]:
    return {
        "version": SCHEMA_VERSION,
        "source": None,
        "phases": [
            {"id": step.id, "label": _humanize(step.id), "steps": [step.id]}
            for step in workflow.steps
        ],
    }


def load_progress_plan(workflow) -> dict[str, Any]:
    """Load and validate presentation-only progress groups for a compiled workflow.

    A sibling ``<workflow>.progress.yaml`` may group logical workflow steps into
    human-readable phases.  If it is absent, every logical workflow step becomes
    its own phase, so progress remains workflow-derived rather than hardcoded.
    """
    if not getattr(workflow, "source", None):
        return _fallback_plan(workflow)
    path = progress_definition_path(workflow)
    if not path.is_file():
        return _fallback_plan(workflow)
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise ProgressPlanError(f"invalid progress definition {path}: {exc}") from exc
    if not isinstance(doc, dict):
        raise ProgressPlanError(f"progress definition must be a mapping: {path}")
    if doc.get("version", SCHEMA_VERSION) != SCHEMA_VERSION:
        raise ProgressPlanError(f"unsupported progress definition version in {path}")
    phases = doc.get("phases")
    if not isinstance(phases, list) or not phases:
        raise ProgressPlanError(f"progress definition requires a non-empty phases list: {path}")

    workflow_ids = [step.id for step in workflow.steps]
    known = set(workflow_ids)
    seen_steps: set[str] = set()
    seen_phases: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(phases, start=1):
        if not isinstance(raw, dict):
            raise ProgressPlanError(f"progress phase {index} must be a mapping: {path}")
        phase_id = str(raw.get("id") or "").strip()
        label = str(raw.get("label") or "").strip()
        steps = raw.get("steps")
        if not phase_id or not label:
            raise ProgressPlanError(f"progress phase {index} requires id and label: {path}")
        if phase_id in seen_phases:
            raise ProgressPlanError(f"duplicate progress phase id {phase_id!r}: {path}")
        if not isinstance(steps, list) or not steps or any(not isinstance(x, str) or not x for x in steps):
            raise ProgressPlanError(f"progress phase {phase_id!r} requires a non-empty string steps list: {path}")
        unknown = [step_id for step_id in steps if step_id not in known]
        if unknown:
            raise ProgressPlanError(
                f"progress phase {phase_id!r} references unknown workflow step(s): {', '.join(unknown)}"
            )
        duplicate = [step_id for step_id in steps if step_id in seen_steps]
        if duplicate:
            raise ProgressPlanError(
                f"workflow step(s) assigned to more than one progress phase: {', '.join(duplicate)}"
            )
        seen_phases.add(phase_id)
        seen_steps.update(steps)
        normalized.append({"id": phase_id, "label": label, "steps": list(steps)})

    missing = [step_id for step_id in workflow_ids if step_id not in seen_steps]
    if missing:
        raise ProgressPlanError(
            f"progress definition does not cover workflow step(s): {', '.join(missing)}"
        )
    return {"version": SCHEMA_VERSION, "source": str(path), "phases": normalized}


class WorkflowProgress:
    """Persist live logical-step state for UI/status consumers."""

    def __init__(self, workflow):
        self.workflow = workflow
        self.workflow_id = getattr(workflow, "workflow_id", None)
        self.workflow_source = getattr(workflow, "source", None)
        self.workflow_sha256 = getattr(workflow, "source_sha256", None)
        self.plan = load_progress_plan(workflow)
        self._status = {step.id: "pending" for step in workflow.steps}
        self._details: dict[str, dict[str, Any]] = {}
        self._path: Path | None = None
        self._executor: str | None = None
        self._loaded = False

    def bind(self, context) -> None:
        path = Path(context.work) / "logs" / "workflow-progress.json"
        if self._path != path:
            self._path = path
            self._executor = getattr(context, "executor", None)
            self._loaded = False
        if not self._loaded:
            self._loaded = True
            self._restore()
            self.write()

    def _restore(self) -> None:
        if not self._path or not self._path.is_file():
            return
        try:
            doc = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            return
        if not isinstance(doc, dict):
            return
        if doc.get("workflow_id") != self.workflow_id:
            return
        if doc.get("workflow_sha256") != self.workflow_sha256:
            return
        rows = doc.get("steps") or []
        for row in rows:
            if not isinstance(row, dict):
                continue
            step_id = row.get("id")
            status = row.get("status")
            if step_id in self._status and status in VALID_STATES:
                # A stale running/failed marker must not block a resumable run.
                self._status[step_id] = "pending" if status in {"running", "failed"} else status

    def status(self, step_id: str) -> str | None:
        return self._status.get(step_id)

    def update(self, step_id: str, status: str, **details: Any) -> None:
        if step_id not in self._status:
            return
        if status not in VALID_STATES:
            raise ValueError(f"invalid workflow progress status {status!r}")
        self._status[step_id] = status
        if details:
            self._details[step_id] = {k: v for k, v in details.items() if v is not None}
        elif status in FINAL_STATES:
            self._details.pop(step_id, None)
        self.write()

    def invalidate(self, step_ids) -> None:
        changed = False
        for step_id in step_ids:
            if step_id in self._status:
                self._status[step_id] = "pending"
                self._details.pop(step_id, None)
                changed = True
        if changed:
            self.write()

    def snapshot(self) -> dict[str, Any]:
        step_rows = []
        for step in self.workflow.steps:
            row = {"id": step.id, "status": self._status[step.id]}
            row.update(self._details.get(step.id, {}))
            step_rows.append(row)

        phases = []
        current_phase = None
        current_step = next((row["id"] for row in step_rows if row["status"] == "running"), None)
        for phase in self.plan["phases"]:
            statuses = [self._status[sid] for sid in phase["steps"]]
            if any(status == "failed" for status in statuses):
                status = "failed"
            elif any(status == "running" for status in statuses):
                status = "running"
            elif all(status in FINAL_STATES for status in statuses):
                status = "completed"
            else:
                status = "pending"
            phases.append({**phase, "status": status})
            if current_phase is None and status in {"running", "failed", "pending"}:
                current_phase = phase["id"]
        complete = bool(step_rows) and all(row["status"] in FINAL_STATES for row in step_rows)
        if complete and phases:
            current_phase = phases[-1]["id"]
        if current_step is None and not complete:
            current_step = next((row["id"] for row in step_rows if row["status"] not in FINAL_STATES), None)

        return {
            "schema_version": SCHEMA_VERSION,
            "workflow_id": self.workflow_id,
            "workflow_definition": str(self.workflow_source) if self.workflow_source is not None else None,
            "workflow_sha256": self.workflow_sha256,
            "progress_definition": self.plan.get("source"),
            "executor": self._executor,
            "complete": complete,
            "current_phase": current_phase,
            "current_step": current_step,
            "phases": phases,
            "steps": step_rows,
        }

    def write(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_name(self._path.name + ".tmp")
        tmp.write_text(json.dumps(self.snapshot(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(self._path)
