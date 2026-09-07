"""Declarative workflow progress planning and live run-state recording."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
FINAL_STATES = {"completed", "skipped"}
VALID_STATES = {"pending", "running", "completed", "skipped", "failed"}


class ProgressPlanError(ValueError):
    """Raised when workflow progress presentation metadata is invalid."""


def _humanize(step_id: str) -> str:
    return step_id.replace("_", " ").replace(".", " · ").strip().title()


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
    """Load and validate UI-only progress groups embedded in a workflow.

    ``presentation.progress_phases`` groups logical workflow steps into
    human-readable UI phases. Presentation metadata cannot affect execution.
    If omitted, every logical step becomes its own phase so progress remains
    workflow-derived rather than hardcoded.
    """
    doc = getattr(workflow, "doc", None) or {}
    presentation = doc.get("presentation") or {}
    phases = presentation.get("progress_phases") if isinstance(presentation, dict) else None
    if phases is None:
        return _fallback_plan(workflow)
    if not isinstance(phases, list) or not phases:
        raise ProgressPlanError("workflow presentation.progress_phases requires a non-empty list")

    workflow_ids = [step.id for step in workflow.steps]
    known = set(workflow_ids)
    seen_steps: set[str] = set()
    seen_phases: set[str] = set()
    normalized: list[dict[str, Any]] = []
    for index, raw in enumerate(phases, start=1):
        if not isinstance(raw, dict):
            raise ProgressPlanError(f"progress phase {index} must be a mapping")
        phase_id = str(raw.get("id") or "").strip()
        label = str(raw.get("label") or "").strip()
        steps = raw.get("steps")
        if not phase_id or not label:
            raise ProgressPlanError(f"progress phase {index} requires id and label")
        if phase_id in seen_phases:
            raise ProgressPlanError(f"duplicate progress phase id {phase_id!r}")
        if not isinstance(steps, list) or not steps or any(not isinstance(x, str) or not x for x in steps):
            raise ProgressPlanError(f"progress phase {phase_id!r} requires a non-empty string steps list")
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
    source = getattr(workflow, "source", None)
    source_label = f"{source}#presentation.progress_phases" if source is not None else None
    return {"version": SCHEMA_VERSION, "source": source_label, "phases": normalized}


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
        self._visible_high_water_index = 0

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
        saved_high = doc.get("visible_high_water_index")
        if isinstance(saved_high, int) and 0 <= saved_high < len(self.plan["phases"]):
            self._visible_high_water_index = max(self._visible_high_water_index, saved_high)
        rows = doc.get("steps") or []
        for row in rows:
            if not isinstance(row, dict):
                continue
            step_id = row.get("id")
            status = row.get("status")
            if step_id in self._status and status in VALID_STATES:
                self._status[step_id] = "pending" if status in {"running", "failed"} else status

    def status(self, step_id: str) -> str | None:
        return self._status.get(step_id)

    def update(self, step_id: str, status: str, **details: Any) -> None:
        if step_id not in self._status:
            return
        if status not in VALID_STATES:
            raise ValueError(f"invalid workflow progress status {status!r}")
        self._status[step_id] = status
        if status in {"running", "completed", "skipped", "failed"}:
            for index, phase in enumerate(self.plan["phases"]):
                if step_id in phase["steps"]:
                    self._visible_high_water_index = max(self._visible_high_water_index, index)
                    break
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

    def _phase_for_step(self, step_id: str | None) -> str | None:
        if not step_id:
            return None
        for phase in self.plan["phases"]:
            if step_id in phase["steps"]:
                return phase["id"]
        return None

    def snapshot(self) -> dict[str, Any]:
        step_rows = []
        for step in self.workflow.steps:
            row = {"id": step.id, "status": self._status[step.id]}
            row.update(self._details.get(step.id, {}))
            step_rows.append(row)

        phases = []
        execution_current_step = next((row["id"] for row in step_rows if row["status"] == "running"), None)
        complete = bool(step_rows) and all(row["status"] in FINAL_STATES for row in step_rows)
        if execution_current_step is None and not complete:
            execution_current_step = next((row["id"] for row in step_rows if row["status"] not in FINAL_STATES), None)
        execution_current_phase = self._phase_for_step(execution_current_step)

        if complete and self.plan["phases"]:
            self._visible_high_water_index = len(self.plan["phases"]) - 1
        high = min(self._visible_high_water_index, max(0, len(self.plan["phases"]) - 1))
        for index, phase in enumerate(self.plan["phases"]):
            statuses = [self._status[sid] for sid in phase["steps"]]
            if "failed" in statuses:
                status = "failed"
            elif complete or index < high:
                status = "completed"
            elif index == high:
                status = "completed" if all(x in FINAL_STATES for x in statuses) and (index == len(self.plan["phases"])-1 or all(self._status[sid] in FINAL_STATES for later in self.plan["phases"][index+1:] for sid in later["steps"])) else "running"
            else:
                status = "pending"
            phases.append({**phase, "status": status})
        visible_current_phase = self.plan["phases"][high]["id"] if self.plan["phases"] else None

        return {
            "schema_version": SCHEMA_VERSION,
            "workflow_id": self.workflow_id,
            "workflow_definition": str(self.workflow_source) if self.workflow_source is not None else None,
            "workflow_sha256": self.workflow_sha256,
            "progress_definition": self.plan.get("source"),
            "executor": self._executor,
            "complete": complete,
            "current_phase": visible_current_phase,
            "visible_current_phase": visible_current_phase,
            "visible_high_water_phase": visible_current_phase,
            "visible_high_water_index": self._visible_high_water_index,
            "execution_current_phase": execution_current_phase,
            "execution_current_step": execution_current_step,
            "current_step": execution_current_step,
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
