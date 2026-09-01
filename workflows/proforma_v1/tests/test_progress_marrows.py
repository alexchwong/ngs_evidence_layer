import json

import pytest
import yaml
from jsonschema import Draft202012Validator
from pathlib import Path

from workflows.proforma_v1 import model_context, runtime, schema_validation


HERE = Path(__file__).resolve().parents[1]
PROMPTS = HERE / "prompts"
SCHEMAS = HERE / "schemas"


def _prompt(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


def _structured_case(*, diagnosis_status=None):
    case = {
        "provisional_disease": "Acute myeloid leukaemia with NPM1 mutation",
        "morphologic_diagnosis_origin": "supplied",
        "bootstrap_cmcs": ["AML"],
        "variants": [],
        "detected_variants_summary": "No NGS variants were detected.",
        "ngs_result_completeness": "complete",
        "ngs_no_variants_detected": [],
        "case_facts": [
            {"fact_id": "C1", "kind": "specimen context", "value": "Day 28 post-treatment marrow."},
            {"fact_id": "C2", "kind": "morphology", "value": "2% blasts, consistent with morphologic remission."},
        ],
    }
    if diagnosis_status is not None:
        case["diagnosis_status"] = diagnosis_status
    return case


def test_structured_case_schema_declares_new_and_progress_without_breaking_legacy_shape():
    schema = json.loads((SCHEMAS / "structured_case.json").read_text(encoding="utf-8"))
    assert schema["properties"]["diagnosis_status"]["enum"] == ["new", "progress"]
    # Legacy saved cases remain schema-compatible because the new field is not required.
    assert "diagnosis_status" not in schema["required"]


def test_runtime_accepts_progress_and_legacy_cases():
    assert runtime.validate_case_text(json.dumps(_structured_case(diagnosis_status="progress"))) == "structured case validated"
    assert runtime.validate_case_text(json.dumps(_structured_case())) == "structured case validated"


def test_legacy_case_projects_as_new_but_progress_is_preserved_for_diagnosis_only():
    legacy = model_context.case_projection(_structured_case(), fields=model_context.DIAGNOSIS_CASE_FIELDS)
    assert legacy["diagnosis_status"] == "new"

    progress = model_context.case_projection(
        _structured_case(diagnosis_status="progress"), fields=model_context.DIAGNOSIS_CASE_FIELDS
    )
    assert progress["diagnosis_status"] == "progress"
    assert "diagnosis_status" not in model_context.DOMAIN_CASE_FIELDS


def test_structure_prompt_separates_new_from_progress_and_preserves_established_disease():
    text = _prompt("structure_case.md")
    assert '"diagnosis_status": "new|progress"' in text
    assert "follow-up, progress, response, restaging, post-treatment, or surveillance" in text
    assert "preserve the explicitly supplied established disease as `provisional_disease`" in text
    assert "they do not replace the underlying disease label" in text
    assert "may indicate progression or transformation" in text


def test_who5_and_icc_progress_rules_are_asymmetric_response_vs_progression():
    for name in ("diagnosis_who5.md", "diagnosis_icc.md"):
        text = _prompt(name)
        assert "Legacy cases without this field are treated as `new`" in text
        assert "treatment response must not downgrade the established disease entity" in text
        assert "do not convert AML to MDS" in text
        assert "must not be used to retrospectively criticize or invalidate the established diagnosis" in text
        assert "protects against treatment-related downgrading; it does not freeze the established disease label" in text
        assert "whether documented at the original diagnosis or in the current specimen" in text
        assert "Historical diagnostic molecular/cytogenetic findings may therefore refine the established disease" in text
        assert "established AML may be refined to AML-MR" in text
        assert "does not block genuine progression or transformation" in text
        assert "blast-phase/transformed disease" in text
        assert "For `diagnosis_status: new`, when no morphologic diagnosis was supplied" in text


def test_demo4_progress_remission_does_not_block_aml_mr_refinement_from_diagnostic_phase_variants():
    for name in ("diagnosis_who5.md", "diagnosis_icc.md"):
        text = _prompt(name)
        assert "Historical diagnostic molecular/cytogenetic findings may therefore refine the established disease" in text
        assert "even when they are no longer detected after therapy" in text
        assert "established AML may be refined to AML-MR" in text
        assert "treatment response must not downgrade the established disease entity" in text




def test_who5_assesses_primary_effects_before_freezing_diagnosis_and_concurrent_pathology():
    text = _prompt("diagnosis_who5.md")
    first = text.index("For each detected variant, first assess")
    combine = text.index("Then combine those conclusions")
    final = text.index("After the primary WHO5 diagnosis is fixed")
    assert first < combine < final
    assert "Complete and freeze that primary WHO5 decision before performing the variant assessments" not in text
    assert "consider only variants that did not contribute to the primary diagnosis" in text
    assert "Mere occurrence in another disease is insufficient" in text


def test_diagnosis_context_renames_negative_gene_list_without_changing_case_schema():
    case = _structured_case(diagnosis_status="progress")
    case["ngs_no_variants_detected"] = ["NPM1", "FLT3"]
    rendered = json.loads(model_context.case_context(case, fields=model_context.DIAGNOSIS_CASE_FIELDS))
    assert rendered["genes_without_detected_ngs_variants"] == ["NPM1", "FLT3"]
    assert "ngs_no_variants_detected" not in rendered
    projected = model_context.case_projection(case, fields=model_context.DIAGNOSIS_CASE_FIELDS)
    assert projected["ngs_no_variants_detected"] == ["NPM1", "FLT3"]


def _icc_yaml(variant_ids):
    rows = "\n".join(
        f"  - variant_id: {vid}\n    classification: nonspecific\n    other_pathology: null\n    reason: assessed"
        for vid in variant_ids
    )
    return (
        "diagnosis: AML\n"
        "diagnostic_effect: unchanged\n"
        "variants: []\n"
        "reason: no ICC refinement\n"
        "variant_assessments:\n"
        f"{rows}\n"
    )


def test_icc_validator_requires_exact_variant_registry_coverage():
    assert schema_validation.validate_icc_diagnosis(
        _icc_yaml(["v01", "v02"]), valid_variants={"v01", "v02"}
    ) == "ICC diagnosis valid"
    with pytest.raises(Exception):
        schema_validation.validate_icc_diagnosis(
            _icc_yaml(["v01"]), valid_variants={"v01", "v02"}
        )


def test_icc_prompt_distinguishes_detected_from_diagnosis_contributing_variants():
    text = _prompt("diagnosis_icc.md")
    assert "variant registry is the authoritative list of detected variants" in text
    assert "Assess every registry variant exactly once" in text
    assert "may be empty and does not indicate NGS negativity" in text
    assert "variant_assessments:" in text
    assert "genes_without_detected_ngs_variants" in text


def test_previous_generic_source_only_strengtheners_removed():
    for name in ("diagnosis_who5.md", "diagnosis_icc.md"):
        text = _prompt(name)
        assert "Summarize and apply only" not in text
        assert "Do not use outside medical knowledge" not in text
        assert "Do not infer diagnostic relationships absent from the cards" not in text


def test_icc_artifact_passes_json_schema_and_exact_variant_coverage():
    text = _icc_yaml(["v01", "v02", "v03", "v04"])
    schema = json.loads((SCHEMAS / "diagnosis.json").read_text(encoding="utf-8"))
    Draft202012Validator(schema).validate(yaml.safe_load(text))
    assert schema_validation.validate_icc_diagnosis(
        text, valid_variants={"v01", "v02", "v03", "v04"}
    ) == "ICC diagnosis valid"
