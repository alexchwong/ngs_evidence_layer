"""Allow-listed deterministic transform extension point."""
from __future__ import annotations

from typing import Any


class TransformError(ValueError):
    pass


def identity(value: Any, context: dict, params: dict) -> Any:
    return value


def derive_diagnostic_cmcs(value: Any, context: dict, params: dict) -> Any:
    from workflows.proforma_v1 import runtime
    return runtime.derive_cmcs(value or {})


def delegated(value: Any, context: dict, params: dict) -> Any:
    """Marker for transforms still implemented by the v6-compatible handler."""
    return value


def reasoning_delegated(value: Any, context: dict, params: dict) -> Any:
    """Reasoning-workflow marker for a cloned deterministic boundary.

    Phase 1 intentionally preserves the shipped default behaviour while giving
    ``reasoning.yaml`` distinct transform identities. Later reasoning phases can
    replace these markers with reasoning-specific implementations without
    changing the transform names used by ``default.yaml``.
    """
    from workflows.proforma_v1 import reasoning_runtime
    return reasoning_runtime.delegated_transform(value, context=context, params=params)


def reasoning_diagnostic(name):
    def apply_reasoning_diagnostic(value: Any, context: dict, params: dict) -> Any:
        from workflows.proforma_v1 import reasoning_runtime
        from workflows.proforma_v1 import reasoning_guards
        reasoning_guards.before_diagnostic_transform(name, context, params)
        result = reasoning_runtime.run_diagnostic_transform(name, context, params)
        return reasoning_guards.after_diagnostic_transform(name, result, context, params)
    return apply_reasoning_diagnostic


def reasoning_ptbg(name):
    def apply_reasoning_ptbg(value: Any, context: dict, params: dict) -> Any:
        from workflows.proforma_v1 import reasoning_runtime
        from workflows.proforma_v1 import reasoning_guards
        reasoning_guards.before_ptbg_transform(name, context, params)
        result = reasoning_runtime.run_ptbg_transform(name, context, params)
        return reasoning_guards.after_ptbg_transform(name, result, context, params)
    return apply_reasoning_ptbg


REGISTRY = {
    "identity": identity,
    "load_corpus": delegated,
    "finalize_diagnosis": delegated,
    "finalize_evidence": delegated,
    "report_blocks": delegated,
    "finalize_report": delegated,
    "consolidate_parallel_variant_rows": delegated,
    "derive_diagnostic_cmcs": derive_diagnostic_cmcs,
    "assess_who1_routing_change": delegated,
    "commit_who1_routing": delegated,
    # ``reasoning.yaml`` owns separate deterministic transform identities so
    # experimental reasoning semantics never require edits to default names.
    "reasoning_load_corpus": reasoning_delegated,
    "reasoning_finalize_evidence": reasoning_delegated,
    "reasoning_report_blocks": reasoning_delegated,
    "reasoning_finalize_report": reasoning_delegated,
    "reasoning_prepare_diagnostic_reasoning": reasoning_diagnostic("reasoning_prepare_diagnostic_reasoning"),
    "reasoning_validate_diagnostic_reasoning_v2": reasoning_diagnostic("reasoning_validate_diagnostic_reasoning_v2"),
    "reasoning_prepare_diagnostic_evidence_match": reasoning_diagnostic("reasoning_prepare_diagnostic_evidence_match"),
    "reasoning_validate_diagnostic_evidence_match": reasoning_diagnostic("reasoning_validate_diagnostic_evidence_match"),
    "reasoning_compile_diagnostic_reasoning": reasoning_diagnostic("reasoning_compile_diagnostic_reasoning"),
    "reasoning_merge_diagnostic_evidence_matches": reasoning_diagnostic("reasoning_merge_diagnostic_evidence_matches"),
    "reasoning_diagnostic_em_audit_review": reasoning_diagnostic("reasoning_diagnostic_em_audit_review"),
    "reasoning_evaluate_diagnoses_v2": reasoning_diagnostic("reasoning_evaluate_diagnoses_v2"),
    "reasoning_prepare_diagnostic_owner": reasoning_diagnostic("reasoning_prepare_diagnostic_owner"),
    "reasoning_validate_diagnostic_owner": reasoning_diagnostic("reasoning_validate_diagnostic_owner"),
    "reasoning_build_diagnostic_registry": reasoning_diagnostic("reasoning_build_diagnostic_registry"),
    "reasoning_collect_diagnostic_owner_assignments": reasoning_diagnostic("reasoning_collect_diagnostic_owner_assignments"),
    "reasoning_prepare_diagnostic_rescue": reasoning_diagnostic("reasoning_prepare_diagnostic_rescue"),
    "reasoning_validate_diagnostic_rescue": reasoning_diagnostic("reasoning_validate_diagnostic_rescue"),
    "reasoning_merge_diagnostic_assignments": reasoning_diagnostic("reasoning_merge_diagnostic_assignments"),
    "reasoning_prepare_diagnostic_evidence_audit": reasoning_diagnostic("reasoning_prepare_diagnostic_evidence_audit"),
    "reasoning_validate_diagnostic_evidence_audit": reasoning_diagnostic("reasoning_validate_diagnostic_evidence_audit"),
    "reasoning_build_diagnostic_disputes": reasoning_diagnostic("reasoning_build_diagnostic_disputes"),
    "reasoning_validate_diagnostic_adjudication": reasoning_diagnostic("reasoning_validate_diagnostic_adjudication"),
    "reasoning_finalize_diagnostic_evidence": reasoning_diagnostic("reasoning_finalize_diagnostic_evidence"),
    "reasoning_prepare_diagnostic_reasoning_audit": reasoning_diagnostic("reasoning_prepare_diagnostic_reasoning_audit"),
    "reasoning_validate_diagnostic_reasoning_audit": reasoning_diagnostic("reasoning_validate_diagnostic_reasoning_audit"),
    "reasoning_evaluate_diagnoses": reasoning_diagnostic("reasoning_evaluate_diagnoses"),
    "reasoning_owner_review": reasoning_diagnostic("reasoning_owner_review"),
    "reasoning_finalize_atomic_diagnosis": reasoning_diagnostic("reasoning_finalize_atomic_diagnosis"),

    "reasoning_prepare_ptbg_reasoning": reasoning_ptbg("reasoning_prepare_ptbg_reasoning"),
    "reasoning_validate_ptbg_reasoning_v2": reasoning_ptbg("reasoning_validate_ptbg_reasoning_v2"),
    "reasoning_prepare_ptbg_evidence_match_v2": reasoning_ptbg("reasoning_prepare_ptbg_evidence_match_v2"),
    "reasoning_validate_ptbg_evidence_match": reasoning_ptbg("reasoning_validate_ptbg_evidence_match"),
    "reasoning_compile_ptbg_reasoning": reasoning_ptbg("reasoning_compile_ptbg_reasoning"),
    "reasoning_merge_ptbg_evidence_matches": reasoning_ptbg("reasoning_merge_ptbg_evidence_matches"),
    "reasoning_ptbg_em_audit_review": reasoning_ptbg("reasoning_ptbg_em_audit_review"),
    "reasoning_ptbg_owner_review_v2": reasoning_ptbg("reasoning_ptbg_owner_review_v2"),
    "reasoning_build_decision_ledger_v2": reasoning_ptbg("reasoning_build_decision_ledger_v2"),
    "reasoning_prepare_ptbg_owner": reasoning_ptbg("reasoning_prepare_ptbg_owner"),
    "reasoning_validate_ptbg_owner": reasoning_ptbg("reasoning_validate_ptbg_owner"),
    "reasoning_build_ptbg_registry": reasoning_ptbg("reasoning_build_ptbg_registry"),
    "reasoning_collect_ptbg_owner_assignments": reasoning_ptbg("reasoning_collect_ptbg_owner_assignments"),
    "reasoning_prepare_ptbg_rescue": reasoning_ptbg("reasoning_prepare_ptbg_rescue"),
    "reasoning_validate_ptbg_rescue": reasoning_ptbg("reasoning_validate_ptbg_rescue"),
    "reasoning_merge_ptbg_assignments": reasoning_ptbg("reasoning_merge_ptbg_assignments"),
    "reasoning_prepare_ptbg_evidence_audit": reasoning_ptbg("reasoning_prepare_ptbg_evidence_audit"),
    "reasoning_validate_ptbg_evidence_audit": reasoning_ptbg("reasoning_validate_ptbg_evidence_audit"),
    "reasoning_build_ptbg_disputes": reasoning_ptbg("reasoning_build_ptbg_disputes"),
    "reasoning_validate_ptbg_adjudication": reasoning_ptbg("reasoning_validate_ptbg_adjudication"),
    "reasoning_finalize_ptbg_evidence": reasoning_ptbg("reasoning_finalize_ptbg_evidence"),
    "reasoning_evaluate_ptbg_direct_applications": reasoning_ptbg("reasoning_evaluate_ptbg_direct_applications"),
    "reasoning_prepare_ptbg_reasoning_audit": reasoning_ptbg("reasoning_prepare_ptbg_reasoning_audit"),
    "reasoning_validate_ptbg_reasoning_audit": reasoning_ptbg("reasoning_validate_ptbg_reasoning_audit"),
    "reasoning_evaluate_ptbg": reasoning_ptbg("reasoning_evaluate_ptbg"),
    "reasoning_ptbg_owner_review": reasoning_ptbg("reasoning_ptbg_owner_review"),
    "reasoning_finalize_atomic_evidence": reasoning_ptbg("reasoning_finalize_atomic_evidence"),
    "reasoning_build_decision_ledger": reasoning_ptbg("reasoning_build_decision_ledger"),
    "reasoning_validate_dissent_summary": reasoning_ptbg("reasoning_validate_dissent_summary"),
    "reasoning_report_blocks": reasoning_ptbg("reasoning_report_blocks"),
    "reasoning_finalize_report": reasoning_ptbg("reasoning_finalize_report"),
}


def apply(name: str, value: Any, *, context: dict | None = None, params: dict | None = None) -> Any:
    if name not in REGISTRY:
        raise TransformError(f"unknown transform {name!r}; registered: {sorted(REGISTRY)}")
    return REGISTRY[name](value, context or {}, params or {})
