"""Shared logical workflow runner consumed by provider and self executors."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from workflows.proforma_v1.engine.context import WorkflowContext


def _dig(value: Any, path: str) -> Any:
    cur = value
    for part in path.split(".") if path else []:
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur


def condition_applies(condition: dict | None, context: WorkflowContext) -> bool:
    if not condition:
        return True
    if "has_items" in condition:
        return bool(context.get(condition["has_items"].get("artifact")))
    if "artifact_true" in condition:
        value = condition["artifact_true"]
        name = value if isinstance(value, str) else value.get("artifact")
        return bool(context.get(name))
    if "artifact_changed" in condition:
        value = condition["artifact_changed"]
        name = value if isinstance(value, str) else value.get("artifact")
        return bool(context.get(f"{name}__changed"))
    if "setting" in condition:
        spec = condition["setting"]
        return _dig(context.get("settings", {}), spec.get("path", "")) == spec.get("equals")
    if "predicate" in condition:
        predicates = context.get("predicates", {}) or {}
        fn = predicates.get(condition["predicate"])
        return bool(fn(context) if callable(fn) else False)
    return False


@dataclass(frozen=True)
class RunResult:
    status: str
    step_id: str | None = None
    handoff: Any = None


class WorkflowRunner:
    def __init__(self, workflow, executor, *, trace=None):
        self.workflow = workflow
        self.executor = executor
        self.trace = trace

    def _record(self, step, status: str, **fields):
        if self.trace is not None:
            self.trace.record(step.id, step.type, status, dependencies=list(step.needs), **fields)

    def _step_done(self, context: WorkflowContext, step_id: str) -> bool:
        if step_id in context.completed:
            return True
        complete = getattr(self.executor, "is_complete", None)
        if callable(complete) and complete(step_id, context):
            context.completed.add(step_id)
            return True
        return False

    def advance(self, context: WorkflowContext) -> RunResult:
        for step in self.workflow.steps:
            if self._step_done(context, step.id):
                continue
            if not all(self._step_done(context, need) for need in step.needs):
                continue
            if not condition_applies(step.when, context):
                context.completed.add(step.id)
                self._record(step, "skipped", reason="condition_false")
                continue
            result = self.executor.execute(step, context) or {}
            status = result.get("status", "complete")
            if status in {"complete", "skipped"}:
                context.completed.add(step.id)
                self._record(step, status, reason=result.get("reason"), executor=context.executor, coalesced_group=result.get("coalesced_group"))
                continue
            if status == "handoff":
                self._record(step, "handoff", executor=context.executor)
                return RunResult("handoff", step.id, result.get("handoff"))
            raise RuntimeError(f"executor returned invalid status {status!r} for {step.id!r}")
        if len(context.completed) == len(self.workflow.steps):
            return RunResult("complete")
        return RunResult("pending")

    def run_all(self, context: WorkflowContext) -> RunResult:
        while True:
            result = self.advance(context)
            if result.status != "pending":
                if result.status == "handoff":
                    raise RuntimeError(f"provider/full runner cannot stop at self handoff {result.step_id!r}")
                return result
