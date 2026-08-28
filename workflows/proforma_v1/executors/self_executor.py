"""Native-self bounded-handoff execution adapter."""
from __future__ import annotations


class SelfExecutor:
    def __init__(self, handlers: dict, *, completion=None, invalidator=None):
        self.handlers = dict(handlers)
        self.completion = completion
        self.invalidator = invalidator

    def is_complete(self, step_id, context):
        return bool(self.completion(step_id, context)) if self.completion else False


    def invalidate(self, step_ids, context):
        if self.invalidator:
            self.invalidator(set(step_ids), context)

    def execute(self, step, context):
        execution = step.execution or {}
        handler_name = execution.get("self_handler")
        if not handler_name or handler_name not in self.handlers:
            raise RuntimeError(f"no self handler registered for {step.id!r}: {handler_name!r}")
        return self.handlers[handler_name](step, context) or {}

    def execute_group(self, steps, context):
        names = {((step.execution or {}).get("self_handler")) for step in steps}
        if len(names) != 1:
            raise RuntimeError(f"self batch has incompatible handlers: {sorted(names)}")
        handler_name = next(iter(names))
        if not handler_name or handler_name not in self.handlers:
            raise RuntimeError(f"no self group handler registered: {handler_name!r}")
        context.put("self_group_steps", tuple(step.id for step in steps))
        context.put("self_group_step_objects", tuple(steps))
        try:
            return self.handlers[handler_name](steps[0], context) or {}
        finally:
            context.put("self_group_steps", ())
            context.put("self_group_step_objects", ())
