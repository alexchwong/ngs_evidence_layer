"""Provider-backed physical execution adapter."""
from __future__ import annotations


def _reasoning_model_proxy(step):
    output = dict(getattr(step, "output", {}) or {})
    output.pop("schema", None)
    try:
        from dataclasses import replace
        return replace(step, output=output)
    except TypeError:
        import copy
        proxy = copy.copy(step)
        proxy.output = output
        return proxy




def _normalize_reasoning_output(step, context):
    from workflows.proforma_v1 import reasoning_runtime
    from workflows.proforma_v1.engine import artifacts as workflow_artifacts

    path = workflow_artifacts.generic_output_path(context.work, step, create=False)
    if not path.is_file():
        return None
    schema_rel = (step.output or {}).get("schema")
    schema = (context.get("workflow").asset_root / schema_rel).resolve() if schema_rel else None
    fmt = str((step.output or {}).get("format") or "yaml")
    raw = path.read_text(encoding="utf-8")
    normalized = reasoning_runtime.normalize_reasoning_artifact(raw, fmt=fmt, schema=schema)
    if normalized.text != raw and not (isinstance(normalized.document, dict) and (normalized.document.get("__reasoning_parse_error__") or normalized.document.get("__reasoning_wrong_artifact__"))):
        path.write_text(normalized.text, encoding="utf-8")
    reasoning_runtime.record_serialization_repairs(context.work, step.id, normalized.repairs)
    artifact = (step.output or {}).get("artifact")
    if artifact:
        context.put(artifact, normalized.document)
    return normalized.document


def _call_reasoning_model(handler, step, context):
    """Run the generic provider handler while observing safe parser cleanup.

    Cleanup can happen inside ``step._prepare_structured`` before this executor
    sees the accepted file.  Observe that bounded call so every deterministic
    reasoning serialization repair is persisted without changing default calls.
    """
    from scripts.core.syntax_repair.adapters import classify_wrong_artifacts, observe_deterministic_repairs
    from workflows.proforma_v1 import reasoning_runtime

    messages = []
    try:
        with classify_wrong_artifacts(), observe_deterministic_repairs(lambda rows: messages.extend(rows)):
            return handler(_reasoning_model_proxy(step), context) or {}
    finally:
        reasoning_runtime.record_serialization_repair_messages(context.work, step.id, messages)


class ProviderExecutor:
    def __init__(self, handlers: dict, *, completion=None, invalidator=None):
        self.handlers = dict(handlers)
        self.completion = completion
        self.invalidator = invalidator
        self.completed_groups: set[str] = set()

    def is_complete(self, step_id, context):
        workflow = context.get("workflow")
        reasoning_step = None
        if workflow is not None:
            try:
                reasoning_step = workflow.step(step_id)
            except KeyError:
                pass
        if reasoning_step is not None and (reasoning_step.execution or {}).get("provider_handler") in {"reasoning_model", "reasoning_optional_model"}:
            from workflows.proforma_v1.engine import artifacts as workflow_artifacts
            path = workflow_artifacts.generic_output_path(context.work, reasoning_step, create=False)
            if path.is_file():
                _normalize_reasoning_output(reasoning_step, context)
                return True
            return False
        done = bool(self.completion(step_id, context)) if self.completion else False
        if done:
            return True
        from workflows.proforma_v1.engine.generic_transform import hydrate
        if hydrate(step_id, context):
            return True
        workflow = context.get("workflow")
        if workflow is not None:
            try:
                step = workflow.step(step_id)
            except KeyError:
                step = None
            if step is not None and (step.execution or {}).get("provider_handler") == "generic_model":
                from workflows.proforma_v1.engine import artifacts as workflow_artifacts
                path = workflow_artifacts.generic_output_path(context.work, step, create=False)
                if path.is_file():
                    artifact = (step.output or {}).get("artifact")
                    if artifact:
                        import json, yaml
                        raw = path.read_text(encoding="utf-8")
                        fmt = str((step.output or {}).get("format") or "yaml")
                        context.put(artifact, json.loads(raw) if fmt == "json" else yaml.safe_load(raw))
                    return True
        return False

    def invalidate(self, step_ids, context):
        if self.invalidator:
            self.invalidator(set(step_ids), context)
        workflow = context.get("workflow")
        if workflow is None:
            return
        from workflows.proforma_v1.engine import artifacts as workflow_artifacts
        for step_id in step_ids:
            try:
                step = workflow.step(step_id)
            except KeyError:
                continue
            handler = (step.execution or {}).get("provider_handler")
            if handler in {"generic_transform", "reasoning_model", "reasoning_optional_model"}:
                workflow_artifacts.generic_output_path(context.work, step, create=False).unlink(missing_ok=True)

    def execute(self, step, context):
        execution = step.execution or {}
        handler_name = execution.get("provider_handler")
        group = execution.get("provider_group")
        if handler_name == "generic_transform":
            from workflows.proforma_v1.engine.generic_transform import execute
            return execute(step, context)
        if handler_name == "reasoning_model":
            handler = self.handlers.get("generic_model")
            if handler is None:
                raise RuntimeError("reasoning_model requires the generic_model provider handler")
            result = _call_reasoning_model(handler, step, context)
            normalized = _normalize_reasoning_output(step, context)
            if normalized is not None:
                result = {**result, "artifact": normalized}
            return result
        if handler_name == "reasoning_optional_model":
            handler = self.handlers.get("generic_model")
            if handler is None:
                raise RuntimeError("reasoning_optional_model requires the generic_model provider handler")
            try:
                result = _call_reasoning_model(handler, step, context)
                normalized = _normalize_reasoning_output(step, context)
                if normalized is not None:
                    result = {**result, "artifact": normalized}
                return result
            except Exception as exc:
                # Presentation-only summaries must never block the clinical report.
                from workflows.proforma_v1.engine import artifacts as workflow_artifacts
                import yaml
                fallback = {"summary": "", "highlights": []}
                path = workflow_artifacts.generic_output_path(context.work, step, create=True)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(yaml.safe_dump(fallback, sort_keys=False), encoding="utf-8")
                artifact = (step.output or {}).get("artifact")
                if artifact:
                    context.put(artifact, fallback)
                return {"status": "complete", "artifact": fallback, "reason": f"optional_model_unavailable: {exc}"}
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
