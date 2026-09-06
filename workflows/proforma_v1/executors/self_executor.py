"""Native-self bounded-handoff execution adapter."""
from __future__ import annotations


def _reasoning_self_pass(step_id: str) -> tuple[str, bool, str]:
    """Describe one bounded frontier-model judgement.

    Reasoning, evidence matching, evidence auditing, reasoning auditing, and
    adjudication are intentionally separate self handoffs.  Deterministic
    transforms may run between them, but never merge judgement types merely to
    reduce physical frontier calls.
    """
    explicit = {
        "diagnosis.who.reason": ("diagnosis_who_reason", "Complete only WHO clinical reasoning. Do not match or cite evidence cards."),
        "diagnosis.who.em": ("diagnosis_who_em", "Match supplied WHO reasoning rules to supplied cards only. Do not alter the clinical reasoning."),
        "diagnosis.icc.reason": ("diagnosis_icc_reason", "Complete only ICC clinical reasoning. Do not match or cite evidence cards."),
        "diagnosis.icc.em": ("diagnosis_icc_em", "Match supplied ICC reasoning rules to supplied cards only. Do not alter the clinical reasoning."),
        "diagnosis.second.reason": ("diagnosis_second_reason", "Complete only second-diagnosis clinical reasoning. Do not match or cite evidence cards."),
        "diagnosis.second.em": ("diagnosis_second_em", "Match supplied second-diagnosis reasoning rules to supplied cards only. Do not alter the clinical reasoning."),
        "diagnosis.evidence.audit": ("diagnosis_evidence_audit", "Audit literature support for the grouped diagnostic assignments only; do not reassess patient applicability."),
        "diagnosis.evidence.adjudication": ("diagnosis_evidence_adjudication", "Adjudicate only disputed diagnostic evidence-support findings."),
        "diagnosis.reasoning.audit": ("diagnosis_reasoning_audit", "Audit patient applicability and diagnostic conclusions only, using evidence-audited rules. Do not rematch evidence."),
        "ptbg.evidence.audit": ("ptbg_evidence_audit", "Audit literature support for grouped PTBG assignments only; do not reassess patient applicability."),
        "ptbg.evidence.adjudication": ("ptbg_evidence_adjudication", "Adjudicate only disputed PTBG evidence-support findings."),
        "ptbg.reasoning.audit": ("ptbg_reasoning_audit", "Audit PTBG patient applicability and conclusions only, using evidence-audited rules. Do not rematch evidence."),
        "dissent.summary": ("final_presentation", "Produce only the ledger-faithful user summary; do not alter clinical decisions."),
    }
    if step_id in explicit:
        pass_id, note = explicit[step_id]
        return pass_id, False, note
    for domain in ("prognosis", "treatment", "biomarker", "germline"):
        if step_id == f"{domain}.reason":
            return f"{domain}_reason", False, f"Complete only {domain} clinical reasoning. Do not match or cite evidence cards."
        if step_id == f"{domain}.em":
            return f"{domain}_em", False, f"Match supplied {domain} reasoning rules to supplied cards only. Do not alter the clinical reasoning."
    return step_id.replace(".", "_"), False, "Complete this bounded reasoning operation only."


def _decorate_reasoning_handoff(result, step_id: str):
    if not isinstance(result, dict) or result.get("status") != "handoff":
        return result
    handoff = result.get("handoff")
    if not isinstance(handoff, dict):
        return result
    manifest = handoff.get("manifest")
    if not isinstance(manifest, dict):
        return result
    pass_id, continuous, note = _reasoning_self_pass(step_id)
    manifest = dict(manifest)
    manifest["self_pass"] = pass_id
    manifest["continue_in_same_frontier_pass"] = continuous
    manifest["self_pass_note"] = note
    handoff = dict(handoff); handoff["manifest"] = manifest
    out = dict(result); out["handoff"] = handoff
    return out




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

class SelfExecutor:
    def __init__(self, handlers: dict, *, completion=None, invalidator=None):
        self.handlers = dict(handlers)
        self.completion = completion
        self.invalidator = invalidator

    def is_complete(self, step_id, context):
        workflow = context.get("workflow")
        reasoning_step = None
        if workflow is not None:
            try:
                reasoning_step = workflow.step(step_id)
            except KeyError:
                pass
        if reasoning_step is not None and (reasoning_step.execution or {}).get("self_handler") in {"reasoning_model", "reasoning_optional_model"}:
            from workflows.proforma_v1.engine import artifacts as workflow_artifacts
            path = workflow_artifacts.generic_output_path(context.work, reasoning_step, create=False)
            if not path.is_file():
                if (reasoning_step.execution or {}).get("self_handler") == "reasoning_optional_model" and reasoning_step.id == "dissent.summary":
                    try:
                        from workflows.proforma_v1 import self_runtime as sr
                        report = sr.output_path(context.work, "report_write", "report-write.yaml")
                    except Exception:
                        report = None
                    if report is not None and report.is_file():
                        import yaml
                        fallback = {"summary": "", "highlights": []}
                        path = workflow_artifacts.generic_output_path(context.work, reasoning_step, create=True)
                        path.parent.mkdir(parents=True, exist_ok=True)
                        path.write_text(yaml.safe_dump(fallback, sort_keys=False), encoding="utf-8")
                    else:
                        return False
                else:
                    return False
            normalized = _normalize_reasoning_output(reasoning_step, context)
            if isinstance(normalized, dict) and normalized.get("__reasoning_parse_error__"):
                feedback = dict(context.get("self_validation_feedback", {}) or {})
                feedback[step_id] = (
                    "Syntax-only repair required. The previous artifact is the intended structured answer but is not parseable. "
                    "Change YAML/JSON serialization only; do not add, remove, correct, reinterpret, summarise, or otherwise change any fact, decision, number, identifier, reason, citation, or ID. "
                    "Return only the complete repaired structured artifact. Parser problem: "
                    + str(normalized.get("__reasoning_parse_error__"))
                )
                context.put("self_validation_feedback", feedback)
                return False
            feedback = dict(context.get("self_validation_feedback", {}) or {})
            feedback.pop(step_id, None)
            context.put("self_validation_feedback", feedback)
            return True
        done = bool(self.completion(step_id, context)) if self.completion else False
        if done:
            return True
        from workflows.proforma_v1.engine.generic_transform import hydrate
        return hydrate(step_id, context)

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
            handler = (step.execution or {}).get("self_handler")
            if handler in {"generic_transform", "reasoning_model", "reasoning_optional_model"}:
                workflow_artifacts.generic_output_path(context.work, step, create=False).unlink(missing_ok=True)

    def execute(self, step, context):
        execution = step.execution or {}
        handler_name = execution.get("self_handler")
        if handler_name == "generic_transform":
            from workflows.proforma_v1.engine.generic_transform import execute
            return execute(step, context)
        if handler_name == "reasoning_model":
            handler = self.handlers.get("generic_model")
            if handler is None:
                raise RuntimeError("reasoning_model requires the generic_model self handler")
            # Self handoffs keep the declared schema visible to the frontier model.
            # Completion deliberately defers semantic/schema acceptance to the
            # following exhaustive reasoning validator.
            return _decorate_reasoning_handoff(handler(step, context) or {}, step.id)
        if handler_name == "reasoning_optional_model":
            handler = self.handlers.get("generic_model")
            if handler is None:
                raise RuntimeError("reasoning_optional_model requires the generic_model self handler")
            return _decorate_reasoning_handoff(handler(step, context) or {}, step.id)
        if not handler_name or handler_name not in self.handlers:
            raise RuntimeError(f"no self handler registered for {step.id!r}: {handler_name!r}")
        return self.handlers[handler_name](step, context) or {}

    def execute_group(self, steps, context):
        names = {((step.execution or {}).get("self_handler")) for step in steps}
        group = (steps[0].execution or {}).get("self_group") if steps else None
        if group == "final_presentation" and names <= {"report_write", "reasoning_optional_model"}:
            operations = {}
            for step in steps:
                handler_name = (step.execution or {}).get("self_handler")
                handler = self.handlers.get("generic_model" if handler_name == "reasoning_optional_model" else handler_name)
                if handler is None:
                    raise RuntimeError(f"final presentation has no self handler for {step.id!r}")
                result = handler(step, context) or {}
                handoff = result.get("handoff") or {}
                if result.get("status") != "handoff" or not isinstance(handoff.get("manifest"), dict):
                    raise RuntimeError(f"final presentation step {step.id!r} did not produce a self handoff")
                operations[step.id] = handoff["manifest"]
            return {"status": "handoff", "handoff": {"stage": "final_presentation", "manifest": {
                "pass": "final_presentation", "self_pass": "final_presentation",
                "continue_in_same_frontier_pass": False,
                "self_pass_note": "Write the report and the ledger-faithful dissent summary in one frontier pass. Neither task may change the immutable decision ledger.",
                "operations": operations,
            }}}
        if len(names) != 1:
            raise RuntimeError(f"self batch has incompatible handlers: {sorted(names)}")
        handler_name = next(iter(names))
        if handler_name == "generic_transform":
            # Deterministic transforms remain individually materialised so their
            # audit/feedback artifacts and replay boundaries stay inspectable.
            result = None
            for step in steps:
                result = self.execute(step, context)
            return result or {"status": "complete"}
        if not handler_name or handler_name not in self.handlers:
            raise RuntimeError(f"no self group handler registered: {handler_name!r}")
        context.put("self_group_steps", tuple(step.id for step in steps))
        context.put("self_group_step_objects", tuple(steps))
        try:
            return self.handlers[handler_name](steps[0], context) or {}
        finally:
            context.put("self_group_steps", ())
            context.put("self_group_step_objects", ())
