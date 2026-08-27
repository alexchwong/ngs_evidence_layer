"""Provider-backed physical execution adapter."""
from __future__ import annotations


class ProviderExecutor:
    def __init__(self, handlers: dict):
        self.handlers = dict(handlers)
        self.completed_groups: set[str] = set()

    def execute(self, step, context):
        execution = step.execution or {}
        handler_name = execution.get("provider_handler")
        group = execution.get("provider_group")
        if not handler_name or handler_name not in self.handlers:
            raise RuntimeError(f"no provider handler registered for {step.id!r}: {handler_name!r}")
        if group and group in self.completed_groups:
            status_map = (context.get("provider_group_status", {}) or {}).get(group, {})
            row = status_map.get(step.id, {})
            return {
                "status": row.get("status", "complete"),
                "coalesced_group": group,
                "reason": row.get("reason", "completed_by_prior_group_member"),
            }
        result = self.handlers[handler_name](step, context) or {}
        if group:
            self.completed_groups.add(group)
            status_map = (context.get("provider_group_status", {}) or {}).get(group, {})
            row = status_map.get(step.id, {})
            return {
                "status": row.get("status", "complete"),
                "coalesced_group": group,
                "reason": row.get("reason"),
                **result,
            }
        return {"status": "complete", **result}
