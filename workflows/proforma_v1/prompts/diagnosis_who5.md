# WHO5 molecular/cytogenetic diagnosis update

## 1. Task and authority

Using only the supplied WHO5 authority cards, decide whether the NGS findings and supplied cytogenetic or other molecular findings refine, supersede, or leave unchanged the starting diagnosis.
Do not use outside medical knowledge or infer diagnostic relationships absent from the supplied cards.

{{ module "deliberate" }}

{{ module "foundational_genetics" }}

{{ module "premise_before_consequence" }}

{{ module "qualifier_check" }}

{{ module "limiting_evidence" }}

{{ module "case_context" }}

{{ module "new_diagnosis" }}

{{ module "progress_testing" }}

{{ module "molecular_result_semantics" }}

## 6. Determine and freeze the primary WHO5 diagnosis

- For each detected variant, first assess its effect on the starting primary disease using all relevant supplied cards. Multiple cards may form an evidence chain, but every link from the finding through any intermediate state to the WHO5 entity must be supported by supplied cards. Do not consider concurrent pathology yet.
- Then combine the variant-specific conclusions with applicable disease-level hierarchy, morphology, cytogenetics, and other molecular findings to determine the most specific underlying WHO5 diagnosis.
- Use one exact supplied `schema_disease` for deterministic routing.
- `diagnostic_effect` must be exactly `unchanged`, `refined`, or `superseded` relative to the starting morphologic diagnosis.
- `variants` contains only variant IDs that materially contribute to the WHO5 diagnosis update; it may be empty.
- `reason` is one concise patient-level proposition about the molecular/cytogenetic effect on diagnosis. Do not relitigate morphology.
- Once the primary WHO5 diagnosis is fixed, do not change it merely because a different detected variant is classified as `diagnostic_for_other_pathology` below.

{{ module "variant_assessment" }}

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
