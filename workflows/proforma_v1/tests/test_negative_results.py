from pathlib import Path

from workflows.proforma_v1 import runtime, schema_validation


HERE = Path(__file__).resolve().parents[1]
PROMPTS = HERE / "prompts"


def _prompt(name: str) -> str:
    return (PROMPTS / name).read_text(encoding="utf-8")


def test_structure_prompt_does_not_promote_descriptive_marrow_to_diagnosis():
    text = _prompt("structure_case.md")
    assert 'provisional_disease: "No morphologic diagnosis supplied"' in text
    assert "Descriptive marrow or tissue findings are not diagnoses" in text
    assert "no_haematological_malignancy" in text
    assert "pending, unavailable, not performed" in text


def test_negative_no_diagnosis_branch_is_explicit_for_who5_and_icc():
    who = _prompt("diagnosis_who5.md")
    icc = _prompt("diagnosis_icc.md")
    for text in (who, icc):
        assert 'diagnosis: "No myeloid neoplasm established from supplied findings"' in text
        assert "pending, unavailable, not performed" in text
        assert "does not exclude a myeloid neoplasm" in text
    assert "schema_disease: no_haematological_malignancy" in who
    assert "variant_assessments: []" in who


def test_existing_diagnosis_contract_accepts_negative_no_established_result():
    who = """\
schema_disease: no_haematological_malignancy
diagnosis: No myeloid neoplasm established from supplied findings
diagnostic_effect: unchanged
variants: []
reason: No NGS variants were detected; the supplied findings do not establish or exclude a myeloid neoplasm, cytogenetics remain pending, and clinical/morphologic correlation is required.
variant_assessments: []
"""
    icc = """\
diagnosis: No myeloid neoplasm established from supplied findings
diagnostic_effect: unchanged
variants: []
reason: No NGS variants were detected; the supplied findings do not establish or exclude a myeloid neoplasm, cytogenetics remain pending, and clinical/morphologic correlation is required.
"""
    schema_validation.validate_who5_diagnosis(
        who,
        allowed_diseases={"no_haematological_malignancy"},
        valid_variants=set(),
    )
    schema_validation.validate_icc_diagnosis(icc, valid_variants=set())


def test_negative_routing_sentinel_does_not_expand_when_bootstrapped_consistently():
    cmcs = runtime.derive_cmcs({"schema_disease": "no_haematological_malignancy"})
    assert cmcs == ["no_haematological_malignancy"]
    assert runtime.has_cmc_expansion(["no_haematological_malignancy"], cmcs) is False


def test_prognosis_guard_preserves_zero_variant_framework_behavior_for_real_diagnoses():
    text = _prompt("prognosis.md")
    assert "return `prognostic_frameworks: []` as well as `classification: []`" in text
    assert "ELN 2022" in text
    assert "zero NGS variants may still receive a framework classification" in text
