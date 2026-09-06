"""Deterministic hardening around reasoning-workflow diagnosis transforms.

These checks intentionally sit outside ``reasoning_runtime`` so the experimental
reasoning workflow can be hardened without changing default proforma semantics.
They add invariant/coherence checks across diagnosis and PTBG owner reasoning;
they do not infer a new clinical conclusion.
"""
from __future__ import annotations

import re
from typing import Any

_AUTHORITIES = {
    "who5": ("diagnosis_who_reasoning", "diagnosis_who_reasoning_validation", "diagnosis_who_evidence_match_validation"),
    "icc": ("diagnosis_icc_reasoning", "diagnosis_icc_reasoning_validation", "diagnosis_icc_evidence_match_validation"),
    "second_diagnosis": ("diagnosis_second_reasoning", "diagnosis_second_reasoning_validation", "diagnosis_second_evidence_match_validation"),
}

_PTBG = {
    "prognosis": ("prognosis_reasoning_validation", "prognosis_evidence_match_validation"),
    "treatment": ("treatment_reasoning_validation", "treatment_evidence_match_validation"),
    "biomarker": ("biomarker_reasoning_validation", "biomarker_evidence_match_validation"),
    "germline": ("germline_reasoning_validation", "germline_evidence_match_validation"),
}

_STOPWORDS = {
    "a", "an", "and", "with", "without", "of", "the", "in", "for", "to", "by",
    "mds", "aml", "cmml", "mpn", "neoplasm", "neoplasms", "leukaemia", "leukemia",
    "myelodysplastic", "acute", "myeloid", "chronic", "mutation", "mutated", "disease",
    "syndrome", "syndromes", "type", "subtype",
}
_DEFINING_CUES = (
    " requires ", " required for ", " is defined by ", " defined by ", " must have ",
    " must contain ", " necessitates ", " is diagnosed when ", " diagnosis requires ",
)


def _ctx(context: dict):
    value = context.get("__workflow_context__") if isinstance(context, dict) else None
    return value if value is not None and hasattr(value, "get") else context


def _get(context: dict, key: str, default=None):
    ctx = _ctx(context)
    if hasattr(ctx, "get"):
        return ctx.get(key, default)
    return default


def _authority(params: dict) -> str:
    explicit = str((params or {}).get("authority") or "")
    if explicit in _AUTHORITIES:
        return explicit
    step_id = str((params or {}).get("step_id") or "")
    if ".who." in f".{step_id}.":
        return "who5"
    if ".icc." in f".{step_id}.":
        return "icc"
    if ".second." in f".{step_id}.":
        return "second_diagnosis"
    raise ValueError(f"cannot infer diagnostic authority from {step_id!r}")


def _tokens(text: Any) -> list[str]:
    return [x for x in re.findall(r"[a-z0-9]+", str(text or "").lower()) if x not in _STOPWORDS and len(x) > 1]


def _canonical_diagnosis(text: Any) -> str:
    value = str(text or "").lower()
    substitutions = (
        (r"\bmyelodysplastic neoplasms?\b", "mds"),
        (r"\bmyelodysplastic syndromes?\b", "mds"),
        (r"\bacute myeloid leukaemia\b", "aml"),
        (r"\bacute myeloid leukemia\b", "aml"),
        (r"\bchronic myelomonocytic leukaemia\b", "cmml"),
        (r"\bchronic myelomonocytic leukemia\b", "cmml"),
    )
    for pattern, replacement in substitutions:
        value = re.sub(pattern, replacement, value)
    return " ".join(re.findall(r"[a-z0-9]+", value))


def _issue(code: str, path: str, message: str, fix: str) -> dict[str, str]:
    return {"code": code, "path": path, "message": message, "fix": fix}


def _walk_reasoning_rows(value: Any, path: str = "$"):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", str(key)) else f"{path}[{key!r}]"
            if key == "reasoning" and isinstance(child, list):
                for index, row in enumerate(child):
                    if isinstance(row, dict):
                        yield f"{child_path}[{index}]", row
            yield from _walk_reasoning_rows(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk_reasoning_rows(child, f"{path}[{index}]")


def reasoning_contract_issues(document: Any) -> list[dict]:
    """Common atomic-reasoning invariants shared by every clinical owner."""
    issues: list[dict] = []
    required = ("rule", "case_fact_ids", "variant_ids", "assessment", "supports_conclusion", "reason")
    for path, row in _walk_reasoning_rows(document):
        missing = [key for key in required if key not in row]
        for key in missing:
            issues.append(_issue(
                "missing_reasoning_field",
                f"{path}.{key}",
                f"atomic reasoning row is missing required field {key!r}",
                f"restore {key!r} while preserving the clinical content of this reasoning row",
            ))
        if row.get("supports_conclusion") is True and row.get("assessment") != "met":
            issues.append(_issue(
                "non_supporting_conclusion_item",
                f"{path}.supports_conclusion",
                f"supports_conclusion is true but assessment is {row.get('assessment')!r}",
                "set supports_conclusion to false unless this reasoning point is assessed as 'met'; do not change the clinical conclusion merely to satisfy this field",
            ))
    return issues


def _merge_validation_issues(result: dict, issues: list[dict]) -> dict:
    if not issues:
        return result
    merged = [*(result.get("issues") or []), *issues]
    # Preserve stable order but avoid duplicate guard/schema reports for the same
    # code/path pair when the underlying JSON schema already reported it.
    unique = []
    seen = set()
    for row in merged:
        key = (row.get("code"), row.get("path"), row.get("message")) if isinstance(row, dict) else repr(row)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    output = dict(result)
    output["status"] = "fail"
    output["issue_count"] = len(unique)
    output["issues"] = unique
    output["feedback"] = _render_feedback(unique)
    return output


def _authoritative_schema_disease(context: dict, domain: str) -> str:
    pack = _get(context, f"{domain}_reasoning_pack") or {}
    diagnosis = pack.get("authoritative_diagnosis") or {} if isinstance(pack, dict) else {}
    who = diagnosis.get("who5") or {} if isinstance(diagnosis, dict) else {}
    return str(who.get("schema_disease") or "") if isinstance(who, dict) else ""


def prognosis_framework_issues(document: Any, *, schema_disease: str) -> list[dict]:
    if not isinstance(document, dict) or str(schema_disease).strip().upper() != "MDS":
        return []
    rows = document.get("frameworks") or []
    names = [str(row.get("name") or "") for row in rows if isinstance(row, dict)]
    issues: list[dict] = []
    if "IPSS-M" not in names:
        issues.append(_issue(
            "missing_required_prognostic_framework",
            "$.frameworks",
            "the authoritative WHO5 disease is MDS but IPSS-M is absent from the framework assessment",
            "retain the exact preset framework name 'IPSS-M' for MDS; a semantic redo must not rename the framework to the disease label or to a cohort study",
        ))
    for index, name in enumerate(names):
        if name and name != "IPSS-M":
            issues.append(_issue(
                "unknown_prognostic_framework",
                f"$.frameworks[{index}].name",
                f"MDS framework name {name!r} is not the accepted preset framework 'IPSS-M'",
                "use the exact framework name 'IPSS-M' and keep non-framework cohort/variant associations under other_evidence",
            ))
    return issues


def _render_feedback(issues: list[dict]) -> str:
    if not issues:
        return ""
    lines = [f"The artifact has {len(issues)} deterministic problem{'s' if len(issues) != 1 else ''}. Fix all of them in one complete redo:"]
    for index, issue in enumerate(issues, 1):
        lines += [
            f"{index}. {issue.get('path') or '$'}",
            f"   What is wrong: {issue.get('message')}",
            f"   What to fix: {issue.get('fix')}",
        ]
    lines += ["", "Return the complete corrected artifact, not a patch. Preserve unrelated clinical decisions and all supplied facts/IDs exactly."]
    return "\n".join(lines) + "\n"


def _case(context: dict, authority: str) -> dict:
    case = _get(context, "case")
    if isinstance(case, dict):
        return case
    pack_key = {"who5": "diagnosis_who_pack", "icc": "diagnosis_icc_pack", "second_diagnosis": "diagnosis_second_pack"}[authority]
    pack = _get(context, pack_key) or {}
    return pack.get("structured_case") or {} if isinstance(pack, dict) else {}


def diagnostic_coherence_issues(document: dict, *, case: dict) -> list[dict]:
    """Return conservative, framework-agnostic diagnosis coherence defects."""
    if not isinstance(document, dict):
        return []
    diagnosis = document.get("diagnosis") or {}
    if not isinstance(diagnosis, dict):
        return []
    issues: list[dict] = []
    label = str(diagnosis.get("label") or "")
    status = diagnosis.get("status")
    effect = diagnosis.get("diagnostic_effect")
    starting = case.get("provisional_disease") if isinstance(case, dict) else None

    # A refinement/supersession must actually change the named diagnostic state.
    if effect in {"refined", "superseded"} and starting and label:
        if _canonical_diagnosis(starting) == _canonical_diagnosis(label):
            issues.append(_issue(
                "incoherent_diagnostic_effect",
                "$.diagnosis.diagnostic_effect",
                f"diagnostic_effect is {effect!r} but the proposed diagnosis {label!r} is unchanged from the authoritative starting diagnosis {starting!r}",
                f"the authoritative starting diagnosis is {starting!r}; set diagnostic_effect to 'unchanged' when the final proposed diagnosis is the same clinical diagnosis, even if a prior failed attempt proposed something different; otherwise return the genuinely refined/superseding diagnosis supported by the reasoning",
            ))

    # Catch the class of contradiction seen in Dublin-10 without encoding TP53
    # or any disease-specific rule: an established proposal cannot coexist with
    # an unmet/unknown rule that explicitly states a requirement for the named
    # proposal. Restrict to requirement language plus substantial label overlap
    # to avoid treating ordinary exclusions/context as defining criteria.
    anchors = set(_tokens(label))
    if status == "established" and anchors:
        threshold = 1 if len(anchors) == 1 else min(2, len(anchors))
        for index, row in enumerate(document.get("reasoning") or []):
            if not isinstance(row, dict) or row.get("assessment") not in {"not_met", "unknown"}:
                continue
            rule = f" {str(row.get('rule') or '').lower()} "
            if not any(cue in rule for cue in _DEFINING_CUES):
                continue
            overlap = anchors.intersection(_tokens(rule))
            if len(overlap) < threshold:
                continue
            issues.append(_issue(
                "unmet_defining_criterion",
                f"$.reasoning[{index}].assessment",
                f"the proposed established diagnosis {label!r} has a defining requirement assessed as {row.get('assessment')!r}: {row.get('rule')}",
                "revise the diagnosis or demonstrate that the defining requirement is met; do not establish a diagnosis whose defining criterion is unmet or unknown",
            ))
    return issues


def after_diagnostic_transform(name: str, result: Any, context: dict, params: dict) -> Any:
    if name != "reasoning_validate_diagnostic_reasoning_v2" or not isinstance(result, dict):
        return result
    authority = _authority(params)
    reasoning_key = _AUTHORITIES[authority][0]
    document = _get(context, reasoning_key) or {}
    extra = [
        *diagnostic_coherence_issues(document, case=_case(context, authority)),
        *reasoning_contract_issues(document),
    ]
    return _merge_validation_issues(result, extra)


def before_diagnostic_transform(name: str, context: dict, params: dict) -> None:
    if name != "reasoning_compile_diagnostic_reasoning":
        return
    authority = _authority(params)
    _reasoning_key, reasoning_validation_key, em_validation_key = _AUTHORITIES[authority]
    failures = []
    for key, label in (
        (reasoning_validation_key, f"diagnosis.{('who' if authority == 'who5' else 'second' if authority == 'second_diagnosis' else 'icc')}.reason.validate"),
        (em_validation_key, f"diagnosis.{('who' if authority == 'who5' else 'second' if authority == 'second_diagnosis' else 'icc')}.em.validate"),
    ):
        artifact = _get(context, key)
        if not isinstance(artifact, dict) or artifact.get("status") != "pass":
            failures.append(label)
    if failures:
        step_id = str((params or {}).get("step_id") or "diagnostic compile")
        raise ValueError(
            f"{step_id} cannot run because prerequisite review(s) did not pass: " + ", ".join(failures)
        )


def _ptbg_domain(params: dict) -> str:
    explicit = str((params or {}).get("domain") or "")
    if explicit in _PTBG:
        return explicit
    step_id = str((params or {}).get("step_id") or "")
    for domain in _PTBG:
        if step_id == f"{domain}.compile" or step_id.startswith(f"{domain}."):
            return domain
    raise ValueError(f"cannot infer PTBG domain from {step_id!r}")


def before_ptbg_transform(name: str, context: dict, params: dict) -> None:
    """Require successful local reason/EM reviews before deterministic PTBG compilation."""
    if name != "reasoning_compile_ptbg_reasoning":
        return
    domain = _ptbg_domain(params)
    reasoning_validation_key, em_validation_key = _PTBG[domain]
    failures = []
    for key, label in (
        (reasoning_validation_key, f"{domain}.reason.validate"),
        (em_validation_key, f"{domain}.em.validate"),
    ):
        artifact = _get(context, key)
        if not isinstance(artifact, dict) or artifact.get("status") != "pass":
            failures.append(label)
    if failures:
        step_id = str((params or {}).get("step_id") or f"{domain}.compile")
        raise ValueError(
            f"{step_id} cannot run because prerequisite review(s) did not pass: " + ", ".join(failures)
        )


def after_ptbg_transform(name: str, result: Any, context: dict, params: dict) -> Any:
    if name != "reasoning_validate_ptbg_reasoning_v2" or not isinstance(result, dict):
        return result
    domain = _ptbg_domain(params)
    document = _get(context, f"{domain}_reasoning") or {}
    extra = reasoning_contract_issues(document)
    if domain == "prognosis":
        extra.extend(prognosis_framework_issues(
            document, schema_disease=_authoritative_schema_disease(context, domain)
        ))
    return _merge_validation_issues(result, extra)
