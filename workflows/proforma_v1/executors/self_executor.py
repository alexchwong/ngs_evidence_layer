"""Native-self bounded-handoff execution adapter."""
from __future__ import annotations


class SelfExecutor:
    def __init__(self, handlers: dict, *, completion=None):
        self.handlers = dict(handlers)
        self.completion = completion
        self.completed_groups: set[str] = set()

    def is_complete(self, step_id, context):
        return bool(self.completion(step_id, context)) if self.completion else False

    def execute(self, step, context):
        execution = step.execution or {}
        handler_name = execution.get("self_handler")
        group = execution.get("self_group")
        if group and group in self.completed_groups:
            return {"status": "complete", "coalesced_group": group, "reason": "completed_by_prior_group_member"}
        if not handler_name or handler_name not in self.handlers:
            raise RuntimeError(f"no self handler registered for {step.id!r}: {handler_name!r}")
        result = self.handlers[handler_name](step, context) or {}
        if group and result.get("status") == "complete":
            self.completed_groups.add(group)
        return result
