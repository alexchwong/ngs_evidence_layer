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


def executor_enabled(step, executor_name: str) -> bool:
    cfg = (step.execution or {}).get(executor_name) or {}
    return cfg.get("enabled", True) is not False


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

    def _ready(self, step, context: WorkflowContext) -> bool:
        return all(self._step_done(context, need) for need in step.needs)

    def _ready_group(self, step, context: WorkflowContext) -> list:
        group = (step.execution or {}).get("self_group")
        if not group or context.executor != "self":
            return [step]
        members = []
        for candidate in self.workflow.steps:
            if candidate.id in context.completed:
                continue
            if (candidate.execution or {}).get("self_group") != group:
                continue
            if not executor_enabled(candidate, context.executor):
                continue
            if self._ready(candidate, context) and condition_applies(candidate.when, context):
                members.append(candidate)
        return members or [step]

    def _review_passed(self, step, context: WorkflowContext, result: dict) -> bool:
        review = step.review
        if not review:
            return True
        verdict = review["verdict"]
        if "predicate" in verdict:
            predicates = context.get("review_predicates", {}) or context.get("predicates", {}) or {}
            fn = predicates.get(verdict["predicate"])
            if not callable(fn):
                raise RuntimeError(f"review predicate {verdict['predicate']!r} is unavailable for {step.id!r}")
            return bool(fn(step, context, result))
        artifact = result.get("artifact")
        if artifact is None:
            artifact_name = (step.output or {}).get("artifact")
            artifact = context.get(artifact_name) if artifact_name else None
        return _dig(artifact, verdict.get("path", "")) in verdict.get("pass_values", [])

    def _descendants_through(self, target_id: str, reviewer_id: str) -> set[str]:
        invalid = {target_id}
        changed = True
        while changed:
            changed = False
            for step in self.workflow.steps:
                if step.id == reviewer_id:
                    continue
                if step.id in invalid:
                    continue
                if any(need in invalid for need in step.needs):
                    invalid.add(step.id)
                    changed = True
        invalid.add(reviewer_id)
        return invalid

    def _handle_review_failure(self, step, context: WorkflowContext, result: dict) -> RunResult | None:
        review = step.review
        on_fail = review["on_fail"]
        if on_fail.get("retry_target"):
            cycles = context.get("review_cycles", {}) or {}
            count = int(cycles.get(step.id, 0)) + 1
            cycles[step.id] = count
            context.put("review_cycles", cycles)
            max_cycles = int(on_fail["max_cycles"])
            if count <= max_cycles:
                feedback = on_fail.get("feedback") or {}
                if feedback:
                    source = feedback["from"]
                    if source.startswith("artifacts."):
                        value = context.get(source.split(".", 1)[1])
                    else:
                        value = result.get("artifact")
                    target = self.workflow.step(review["target"])
                    binding = (target.inputs or {}).get(feedback["as"]) or {}
                    ref = binding.get("from")
                    if not isinstance(ref, str) or not ref.startswith("feedback."):
                        raise RuntimeError(
                            f"review feedback alias {feedback['as']!r} on {target.id!r} is not bound to feedback.*"
                        )
                    fb = dict(context.get("feedback_values", {}) or {})
                    fb[ref] = value
                    context.put("feedback_values", fb)
                invalid = self._descendants_through(review["target"], step.id)
                context.completed.difference_update(invalid)
                invalidate = getattr(self.executor, "invalidate", None)
                if callable(invalidate):
                    invalidate(invalid, context)
                self._record(step, "feedback", reason="review_failed_retry", target=review["target"], cycle=count)
                return RunResult("pending", review["target"])
            exhausted = on_fail.get("exhausted") or {"action": "stop"}
            action = exhausted.get("action", "stop")
            if action == "stop":
                raise RuntimeError(f"review {step.id!r} failed after {max_cycles} feedback cycle(s)")
            if action == "route_to":
                context.put("forced_route", exhausted.get("route_to"))
            elif action == "suppress":
                context.put(f"{review['target']}__suppressed", True)
            elif action == "continue_with_dissent":
                context.put(f"{step.id}__dissent", True)
            return None
        if on_fail.get("route_to"):
            context.put("forced_route", on_fail["route_to"])
            self._record(step, "review_failed", reason="route_to", route_to=on_fail["route_to"])
            return None
        raise RuntimeError(f"review {step.id!r} has no executable on_fail policy")

    def _execute_one(self, step, context: WorkflowContext) -> RunResult | None:
        if not executor_enabled(step, context.executor):
            context.completed.add(step.id)
            self._record(step, "skipped", reason="executor_disabled", executor=context.executor)
            return None
        if not condition_applies(step.when, context):
            context.completed.add(step.id)
            self._record(step, "skipped", reason="condition_false", executor=context.executor)
            return None

        group_steps = self._ready_group(step, context)
        if len(group_steps) > 1 and hasattr(self.executor, "execute_group"):
            result = self.executor.execute_group(group_steps, context) or {}
            status = result.get("status", "complete")
            if status == "handoff":
                for member in group_steps:
                    self._record(member, "handoff", executor=context.executor, coalesced_group=(member.execution or {}).get("self_group"))
                return RunResult("handoff", step.id, result.get("handoff"))
            if status not in {"complete", "skipped"}:
                raise RuntimeError(f"executor returned invalid group status {status!r}")
            for member in group_steps:
                context.completed.add(member.id)
                self._record(member, status, executor=context.executor, coalesced_group=(member.execution or {}).get("self_group"), reason=result.get("reason"))
            return None

        result = self.executor.execute(step, context) or {}
        status = result.get("status", "complete")
        if status in {"complete", "skipped"}:
            if status == "complete" and step.review and not self._review_passed(step, context, result):
                context.completed.add(step.id)
                return self._handle_review_failure(step, context, result)
            context.completed.add(step.id)
            self._record(step, status, reason=result.get("reason"), executor=context.executor, coalesced_group=result.get("coalesced_group"))
            return None
        if status == "handoff":
            self._record(step, "handoff", executor=context.executor)
            return RunResult("handoff", step.id, result.get("handoff"))
        raise RuntimeError(f"executor returned invalid status {status!r} for {step.id!r}")

    def advance(self, context: WorkflowContext) -> RunResult:
        forced = context.get("forced_route")
        if forced:
            context.put("forced_route", None)
            step = self.workflow.step(forced)
            if not self._ready(step, context):
                raise RuntimeError(f"forced route {forced!r} is not runnable")
            routed = self._execute_one(step, context)
            if routed:
                return routed

        for step in self.workflow.steps:
            if self._step_done(context, step.id):
                continue
            if not self._ready(step, context):
                continue
            result = self._execute_one(step, context)
            if result:
                return result
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
