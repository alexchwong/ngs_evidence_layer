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
import re
import yaml

from workflows.proforma_v1 import default_config

CASE_FIELDS = ("provisional_disease", "diagnosis_status", "morphologic_diagnosis_origin", "case_facts", "detected_variants_summary", "ngs_result_completeness", "ngs_no_variants_detected")
ALLOWED_CASE_FIELDS = CASE_FIELDS + ("patient_age",)
DIAGNOSIS_CASE_FIELDS = ("provisional_disease", "diagnosis_status", "morphologic_diagnosis_origin", "case_facts", "ngs_result_completeness", "ngs_no_variants_detected")
DOMAIN_CASE_FIELDS = ("provisional_disease", "case_facts", "ngs_result_completeness", "ngs_no_variants_detected")
GERMLINE_CASE_FIELDS = ("provisional_disease", "patient_age", "case_facts", "ngs_result_completeness", "ngs_no_variants_detected")
DEFAULT_REGISTRY_FIELDS = ("gene", "description", "protein_alias")
GERMLINE_REGISTRY_FIELDS = ("gene", "description", "protein_alias", "event_type", "vaf")
DIAGNOSIS_REGISTRY_FIELDS = ("gene", "description", "protein_alias", "event_type", "vaf")
DOMAIN_DIAGNOSIS_FIELDS = ("schema_disease", "diagnosis", "variants")

_AMINO_ACID_3_TO_1 = {
    "Ala": "A", "Arg": "R", "Asn": "N", "Asp": "D", "Cys": "C",
    "Gln": "Q", "Glu": "E", "Gly": "G", "His": "H", "Ile": "I",
    "Leu": "L", "Lys": "K", "Met": "M", "Phe": "F", "Pro": "P",
    "Ser": "S", "Thr": "T", "Trp": "W", "Tyr": "Y", "Val": "V",
}
_SIMPLE_PROTEIN_SUBSTITUTION = re.compile(
    r"(?<![A-Za-z0-9])p\.?\(?(?P<ref>Ala|Arg|Asn|Asp|Cys|Gln|Glu|Gly|His|Ile|Leu|Lys|Met|Phe|Pro|Ser|Thr|Trp|Tyr|Val)(?P<pos>[1-9][0-9]*)(?P<alt>Ala|Arg|Asn|Asp|Cys|Gln|Glu|Gly|His|Ile|Leu|Lys|Met|Phe|Pro|Ser|Thr|Trp|Tyr|Val)\)?(?![A-Za-z0-9])"
)


def protein_substitution_alias(description: str | None) -> str | None:
    """Return a one-letter alias only for an unambiguous simple protein substitution."""
    if not isinstance(description, str):
        return None
    matches = list(_SIMPLE_PROTEIN_SUBSTITUTION.finditer(description))
    if len(matches) != 1:
        return None
    match = matches[0]
    return f"{_AMINO_ACID_3_TO_1[match.group('ref')]}{match.group('pos')}{_AMINO_ACID_3_TO_1[match.group('alt')]}"


def _protein_alias_enabled() -> bool:
    """Return the selected v1 protein-alias enrichment state."""
    spec = default_config.enrichment_spec("protein_hgvs_one_letter_alias")
    if spec["version"] != "v1":
        raise ValueError(
            f"unsupported protein_hgvs_one_letter_alias version {spec['version']!r}; supported: v1"
        )
    return bool(spec["enabled"])


def _yaml(doc) -> str:
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=110)


def canonical_registry(reg: dict, *, fields=DEFAULT_REGISTRY_FIELDS) -> dict:
    """Return the requested canonical registry projection with source IDs removed."""
    allowed=set(DEFAULT_REGISTRY_FIELDS)|set(GERMLINE_REGISTRY_FIELDS)|{"protein_alias"}
    unknown=[f for f in fields if f not in allowed]
    if unknown:
        raise ValueError(f"unknown variant-registry projection field(s): {unknown}")
    out = {}
    alias_enabled = _protein_alias_enabled()
    for vid, row in (reg or {}).items():
        if not isinstance(row, dict):
            continue
        projected = {field: row.get(field) for field in fields if field in row}
        if "protein_alias" in fields:
            if not alias_enabled:
                projected.pop("protein_alias", None)
            elif "protein_alias" not in projected:
                alias = protein_substitution_alias(row.get("description"))
                if alias is not None:
                    projected["protein_alias"] = alias
        out[vid] = projected
    return out


def registry_context(reg: dict, *, fields=DEFAULT_REGISTRY_FIELDS) -> str:
    return _yaml({"variants": canonical_registry(reg, fields=fields)})


def case_projection(case: dict, *, fields=CASE_FIELDS) -> dict:
    unknown = [f for f in fields if f not in ALLOWED_CASE_FIELDS]
    if unknown:
        raise ValueError(f"unknown structured-case projection field(s): {unknown}")
    out = {f: case.get(f) for f in fields if f in (case or {})}
    if "diagnosis_status" in fields and "diagnosis_status" not in out:
        out["diagnosis_status"] = "new"
    return out


def case_context(case: dict, *, fields=CASE_FIELDS) -> str:
    doc = case_projection(case, fields=fields)
    if fields == DIAGNOSIS_CASE_FIELDS and "ngs_no_variants_detected" in doc:
        doc["genes_without_detected_ngs_variants"] = doc.pop("ngs_no_variants_detected")
    return json.dumps(doc, indent=2, ensure_ascii=False)


def diagnosis_projection(diagnosis: dict, *, fields=DOMAIN_DIAGNOSIS_FIELDS) -> dict:
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
    return _yaml(diagnosis_projection(diagnosis, fields=fields))


def assert_canonical(text: str, *, source_ids) -> None:
    leaked = sorted({sid for sid in source_ids or () if sid and _whole_word(text, sid)})
    if leaked:
        raise AssertionError(
            f"source-case variant IDs leaked into model context: {leaked}; "
            "downstream prompts must expose canonical IDs only"
        )


def _whole_word(text: str, token: str) -> bool:
    return re.search(rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])", text or "") is not None


def source_ids(reg: dict) -> list[str]:
    out = []
    for row in (reg or {}).values():
        if isinstance(row, dict) and isinstance(row.get("variant_id"), str):
            out.append(row["variant_id"])
    return out
