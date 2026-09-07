# WHO5 molecular/cytogenetic diagnosis update

## 1. Task and authority

Using only the supplied WHO5 authority cards, decide whether the NGS findings and supplied cytogenetic or other molecular findings refine, supersede, or leave unchanged the starting diagnosis.
Do not use outside medical knowledge or infer diagnostic relationships absent from the supplied cards.

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

## 5. Molecular and cytogenetic result semantics

{{ include "../includes/diagnosis/molecular_result_semantics.md" }}

## 6. Determine and freeze the primary WHO5 diagnosis

- For each detected variant, first assess its effect on the starting primary disease using all relevant supplied cards. Multiple cards may form an evidence chain, but every link from the finding through any intermediate state to the WHO5 entity must be supported by supplied cards. Do not consider concurrent pathology yet.
- Then combine the variant-specific conclusions with applicable disease-level hierarchy, morphology, cytogenetics, and other molecular findings to determine the most specific underlying WHO5 diagnosis.
- Use one exact supplied `schema_disease` for deterministic routing.
- `diagnostic_effect` must be exactly `unchanged`, `refined`, or `superseded` relative to the starting morphologic diagnosis.
- `variants` contains only variant IDs that materially contribute to the WHO5 diagnosis update; it may be empty.
- `reason` is one concise patient-level proposition about the molecular/cytogenetic effect on diagnosis. Do not relitigate morphology.
- Once the primary WHO5 diagnosis is fixed, do not change it merely because a different detected variant is classified as `diagnostic_for_other_pathology` below.

## 7. Assess every detected variant

{{ include "../includes/diagnosis/variant_assessment.md" }}

## 8. Output contract

Return YAML only:
```yaml
schema_disease: "<allowed schema disease>"
diagnosis: "<WHO5 diagnosis>"
diagnostic_effect: "<unchanged|refined|superseded>"
variants: [v01]
reason: "<one concise reason>"
variant_assessments:
  - variant_id: v01
    classification: "<diagnostic_for_primary|nonspecific|diagnostic_for_other_pathology>"
    other_pathology: null
    reason: "<one concise variant-level reason>"
```
