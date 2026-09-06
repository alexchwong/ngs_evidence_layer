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



def _reviewed_text_coherence_flags(diagnosis: Any) -> list[dict[str, str]]:
    """Conservative text-only flags; never infer a replacement diagnosis."""
    import re
    flags: list[dict[str, str]] = []
    if not isinstance(diagnosis, dict):
        return flags
    stop = {"a", "an", "and", "with", "without", "of", "the", "in", "for", "to", "by"}
    for authority in ("who5", "icc"):
        row = diagnosis.get(authority)
        if not isinstance(row, dict):
            continue
        label = str(row.get("diagnosis") or "")
        reason = str(row.get("reason") or "")
        tokens = [t for t in re.findall(r"[a-z0-9]+", label.lower()) if len(t) > 2 and t not in stop]
        lower = reason.lower()
        for token in tokens:
            patterns = (rf"\bnot\s+{re.escape(token)}\b", rf"\bwithout\s+{re.escape(token)}\b")
            if any(re.search(pattern, lower) for pattern in patterns):
                flags.append({
                    "code": "negated_diagnosis_term",
                    "path": f"diagnosis.{authority}.reason",
                    "message": f"diagnosis label contains {token!r} but the reason explicitly negates that same term",
                })
                break
    return flags

def default_reviewed_clinical_packet(value: Any, context: dict, params: dict) -> Any:
    """Freeze the clinically relevant default-proforma state for one audit call.

    This is deliberately a projection, not a clinical inference.  Native-self
    resumes in a fresh process between frontier handoffs, so this boundary must
    be able to hydrate the established default artifacts from disk rather than
    relying on transient context alone.  No card filtering or clinical rewrite
    occurs here.
    """
    from pathlib import Path
    from workflows.proforma_v1 import self_runtime as sr

    ctx = context.get("__workflow_context__") if isinstance(context, dict) else None
    get = ctx.get if ctx is not None and hasattr(ctx, "get") else context.get
    work = Path(context.get("__work__") or getattr(ctx, "work", "."))

    case = get("case")
    diagnosis = get("diagnosis")
    domains = get("domains") or {}
    assignments = get("evidence_assignments")
    audits = get("evidence_audits")
    adjudication = get("evidence_adjudication")

    # The provider runner normally carries these objects in memory. Native-self
    # does not, because each handoff is resumed by a new process. Hydrate only
    # missing values from the canonical files already required upstream.
    if case is None:
        case, _registry = sr.load_case_registry(work)
    if diagnosis is None:
        diagnosis = sr.finalize_diagnosis(work)
    if not domains:
        domains = sr.load_domains(work)

    def read_if_present(group: str, name: str):
        path = sr.output_path(work, group, name)
        return sr.read_yaml(path) if path.is_file() else None

    if assignments is None:
        assignments = read_if_present("evidence_matches", "self-resolution.yaml")
    if audits is None:
        audits = read_if_present("evidence_audits", "self-audit.yaml")
    if adjudication is None:
        adjudication = read_if_present("evidence_adjudication", "adjudication.yaml")

    return {
        "structured_case": case,
        "diagnosis": diagnosis,
        "deterministic_coherence_flags": _reviewed_text_coherence_flags(diagnosis),
        "domains": domains,
        "evidence_assignments": assignments,
        "evidence_audits": audits,
        "evidence_adjudication": adjudication,
    }


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
    "default_reviewed_clinical_packet": default_reviewed_clinical_packet,
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
