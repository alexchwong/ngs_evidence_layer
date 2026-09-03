"""Canonical downstream model context for proforma-v1.

Downstream clinical owner models must see exactly one identifier namespace for a
variant: the canonical workflow ID (``v01``, ``v02``, ...).  Source-case IDs
(``V1``, ``V2``, ...) are provenance only.  They are retained in the variant
registry artifact on disk and are never rendered into a model prompt.
This module owns two responsibilities:
1. **Namespace hygiene** — strip the source ``variant_id`` from anything a model
   sees, and never emit the raw structured case (which carries ``V1``) next to a
   canonical registry.
2. **Projection** — give each stage only the fields it needs.  Every prompt in
   v6 previously received the complete structured case, the complete registry
   and the complete diagnosis object.  For a low-active-parameter model that is
   instruction dilution: the stage's own task competes with several thousand
   tokens of upstream reasoning it cannot act on.
Nothing here calls a model, validates an artifact, or makes a clinical decision.
Each function is a pure transform and is directly testable with a literal dict.
"""
from __future__ import annotations
import json
import yaml
# Fields of the structured case that a downstream stage may ask for.  ``variants``
# is deliberately absent: the canonical registry is the only variant view a
# downstream model is given. patient_age is allowed only for the germline-specific
# projection so existing non-germline prompt context is unchanged.
CASE_FIELDS = ("provisional_disease", "diagnosis_status", "morphologic_diagnosis_origin", "case_facts", "detected_variants_summary", "ngs_result_completeness", "ngs_no_variants_detected")
ALLOWED_CASE_FIELDS = CASE_FIELDS + ("patient_age",)
# Default projections per stage family.  These are the reviewable trim decisions;
# widening one is a one-line change here rather than an edit to step.py.
DIAGNOSIS_CASE_FIELDS = ("provisional_disease", "diagnosis_status", "morphologic_diagnosis_origin", "case_facts", "ngs_result_completeness", "ngs_no_variants_detected")
DOMAIN_CASE_FIELDS = ("provisional_disease", "case_facts", "ngs_result_completeness", "ngs_no_variants_detected")
GERMLINE_CASE_FIELDS = ("provisional_disease", "patient_age", "case_facts", "ngs_result_completeness", "ngs_no_variants_detected")
DEFAULT_REGISTRY_FIELDS = ("gene", "description")
GERMLINE_REGISTRY_FIELDS = ("gene", "description", "event_type", "vaf")
# Domain (PTBG) stages classify variants.  They need to know *what* the disease
# was called, not the diagnostic argument for it.  Dropping the free-text
# `reason` paragraphs from the three diagnosis objects is the single largest
# token reduction in the domain prompts.  Widen this tuple to re-include them.
DOMAIN_DIAGNOSIS_FIELDS = ("schema_disease", "diagnosis", "variants")

def _yaml(doc) -> str:
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=110)

def canonical_registry(reg: dict, *, fields=DEFAULT_REGISTRY_FIELDS) -> dict:
    """Return the requested canonical registry projection with source IDs removed.
    ``reg`` is keyed by canonical ID and each row carries ``variant_id`` (the
    ``V1``-style source ID) for provenance.  That field must never reach a model:
    it is the identifier the deterministic validators reject, and a model shown
    both namespaces will reproduce whichever appeared more often.

    Molecular event type and VAF are deliberately exposed only through the
    germline-specific projection; diagnosis, prognosis, treatment and biomarker
    prompts retain their existing registry view.
    """
    allowed=set(DEFAULT_REGISTRY_FIELDS)|set(GERMLINE_REGISTRY_FIELDS)
    unknown=[f for f in fields if f not in allowed]
    if unknown:
        raise ValueError(f"unknown variant-registry projection field(s): {unknown}")
    out = {}
    for vid, row in (reg or {}).items():
        if not isinstance(row, dict):
            continue
        out[vid] = {field: row.get(field) for field in fields if field in row}
    return out

def registry_context(reg: dict, *, fields=DEFAULT_REGISTRY_FIELDS) -> str:
    """Render a canonical variant-registry projection as a model-facing YAML block."""
    return _yaml({"variants": canonical_registry(reg, fields=fields)})


def case_projection(case: dict, *, fields=CASE_FIELDS) -> dict:
    """Return only the requested structured-case fields.
    ``variants`` is never included.  Callers that need variant identity supply
    ``registry_context`` alongside this projection.
    Legacy structured cases predate ``diagnosis_status``.  When a caller asks
    for that field and it is absent, project ``new`` so old saved runs retain the
    pre-existing de-novo diagnostic behaviour rather than failing or entering a
    progress-marrow branch accidentally.
    """
    unknown = [f for f in fields if f not in ALLOWED_CASE_FIELDS]
    if unknown:
        raise ValueError(f"unknown structured-case projection field(s): {unknown}")
    out = {f: case.get(f) for f in fields if f in (case or {})}
    if "diagnosis_status" in fields and "diagnosis_status" not in out:
        out["diagnosis_status"] = "new"
    return out

def case_context(case: dict, *, fields=CASE_FIELDS) -> str:
    """Render a structured-case projection as a model-facing JSON block."""
    doc = case_projection(case, fields=fields)
    if fields == DIAGNOSIS_CASE_FIELDS and "ngs_no_variants_detected" in doc:
        doc["genes_without_detected_ngs_variants"] = doc.pop("ngs_no_variants_detected")
    return json.dumps(doc, indent=2, ensure_ascii=False)

def diagnosis_projection(diagnosis: dict, *, fields=DOMAIN_DIAGNOSIS_FIELDS) -> dict:
    """Return the primary framework diagnoses reduced to the requested fields.
    ``relationship`` is always retained: it is one token and it is the only part
    of the diagnosis object a downstream stage cannot re-derive.
    """
    out = {}
    for role in ("who5", "icc"):
        row = (diagnosis or {}).get(role)
        if not isinstance(row, dict):
            continue
        projected = {f: row[f] for f in fields if f in row}
        if projected:
            out[role] = projected
    if (diagnosis or {}).get("relationship") is not None:
        out["relationship"] = diagnosis["relationship"]
    return out

def diagnosis_context(diagnosis: dict, *, fields=DOMAIN_DIAGNOSIS_FIELDS) -> str:
    """Render a diagnosis projection as a model-facing YAML block."""
    return _yaml(diagnosis_projection(diagnosis, fields=fields))

def assert_canonical(text: str, *, source_ids) -> None:
    """Fail loudly if a source-case ID reached a model-facing prompt.
    This is a development guard, not a validator: it protects the invariant that
    the ``V1``/``v01`` collision cannot silently return via a new prompt block.
    """
    leaked = sorted({sid for sid in source_ids or () if sid and _whole_word(text, sid)})
    if leaked:
        raise AssertionError(
            f"source-case variant IDs leaked into model context: {leaked}; "
            "downstream prompts must expose canonical IDs only"
        )

def _whole_word(text: str, token: str) -> bool:
    import re

    return re.search(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])", text or "") is not None


def source_ids(reg: dict) -> list[str]:
    """Source-case IDs currently held in the registry, for the guard above."""
    out = []
    for row in (reg or {}).values():
        if isinstance(row, dict) and isinstance(row.get("variant_id"), str):
            out.append(row["variant_id"])
    return out
