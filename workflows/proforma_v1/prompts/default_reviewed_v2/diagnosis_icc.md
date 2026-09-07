# ICC molecular/cytogenetic diagnosis update

## 1. Task and authority

Using only the supplied ICC authority cards, decide whether the NGS findings and supplied cytogenetic or other molecular findings refine, supersede, or leave unchanged the starting diagnosis under ICC.
Do not use outside medical knowledge or infer diagnostic relationships absent from the supplied cards.
The WHO5 diagnosis is supplied only as context. Do not alter it and do not write a separate WHO5/ICC comparison.

## Reasoning correction

`reasoning_correction` below is `null` on the first pass; ignore this section entirely when it is.

When it is supplied, your previous answer to this same task failed an independent reasoning review. You are given your previous output and, in `correction_brief`, the specific reasoning defect the reviewer identified.

Carry out the **full task again** from the original case, findings and cards supplied below. This is a fresh clinical reassessment, not a wording repair.

- Do not repeat the identified reasoning error.
- Do not merely rewrite the reason text to satisfy the criticism while leaving the same conclusion standing. If the identified defect removes the support for your previous conclusion, the conclusion must be reconsidered, along with every field that depended on it.
- If, having reconsidered, you judge that your previous conclusion still holds on the supplied findings, you may return it — but state the derivation that actually supports it rather than the one the reviewer rejected.
- Everything not touched by the identified defect should be reassessed on its merits, not preserved by default.

The reviewer identifies faulty inference. It does not decide the clinical answer and has not been told what the answer should be. That decision remains yours.

{{ input.reasoning_correction }}

## 2. Determine case context

{{ include "../includes/diagnosis/case_context.md" }}

## 3. New diagnosis

{{ include "../includes/diagnosis/new_diagnosis.md" }}

## 4. Progress testing

{{ include "../includes/diagnosis/progress_testing.md" }}

For ICC specifically:
- Negative NGS during `progress`, including loss of a previously detected disease-defining variant, is a current molecular response/MRD observation and must not be used to retrospectively criticize or invalidate the established diagnosis.
- Retain the established disease and describe the current treated/response state concisely in `reason`; response findings do not convert AML to MDS, MDS to CCUS, an established neoplasm to `no_haematological_malignancy`, or otherwise move the disease backwards to a lesser entity.
- Historical diagnostic findings may refine established AML to AML-MR when supplied diagnostic-phase findings meet the relevant ICC criteria.
- A prior MPN with a current blast percentage meeting blast-phase criteria may be classified as blast-phase/transformed disease when the supplied ICC authority supports that change.

## 5. Molecular and cytogenetic result semantics

{{ include "../includes/diagnosis/molecular_result_semantics.md" }}

## 6. Determine and freeze the primary ICC diagnosis

- Return one ICC diagnosis only.
- `diagnostic_effect` must be exactly `unchanged`, `refined`, or `superseded` relative to the starting morphologic diagnosis.
- `variants` contains only variant IDs that materially contribute to the ICC diagnosis update; it may be empty and does not indicate NGS negativity.
- `reason` is one concise patient-level proposition about the molecular/cytogenetic effect on diagnosis. Do not relitigate morphology.
- Once the primary ICC diagnosis is fixed, do not change it merely because a different detected variant is classified as `diagnostic_for_other_pathology` below.

## 7. Assess every detected variant

{{ include "../includes/diagnosis/variant_assessment.md" }}

## 8. Output contract

For the Section 3 no-established-neoplasm fallback only, also include `schema_disease: no_haematological_malignancy`; otherwise omit `schema_disease`.

Return YAML only:
```yaml
diagnosis: "<ICC diagnosis>"
diagnostic_effect: "<unchanged|refined|superseded>"
variants: [v01]
reason: "<one concise reason>"
variant_assessments:
  - variant_id: v01
    classification: "<diagnostic_for_primary|nonspecific|diagnostic_for_other_pathology>"
    other_pathology: null
    reason: "<one concise variant-level reason>"
```
