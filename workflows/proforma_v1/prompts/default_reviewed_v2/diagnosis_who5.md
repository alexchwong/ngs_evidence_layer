# WHO5 molecular/cytogenetic diagnosis update

## 1. Task and authority

Using only the supplied WHO5 authority cards, decide whether the NGS findings and supplied cytogenetic or other molecular findings refine, supersede, or leave unchanged the starting diagnosis.
Do not use outside medical knowledge or infer diagnostic relationships absent from the supplied cards.

## Reasoning correction

{{ include "../includes/reasoning_correction.md" }}

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
- Once the primary WHO5 diagnosis is fixed, do not change it merely because a different detected variant is classified as `suspicious_for_other_pathology` below.

## 7. Assess every detected variant

After the final primary WHO5 diagnosis is frozen, classify every detected registry variant exactly once in `variant_assessments`, relative to that final WHO5 diagnosis. The variant registry is the authoritative list of detected variants; when it is empty, return `variant_assessments: []`.

- `diagnostic_for_primary`: the variant is diagnostic/disease-defining for the final primary WHO5 disease. A variant that promotes or supersedes the starting morphology into the final WHO5 disease belongs here, not under another pathology.
- `nonspecific`: the variant does not provide a sufficiently strong diagnostic signal for either the final primary WHO5 disease or a distinct other pathology. Common cross-disease mutations, broad associations, prognostic-only findings, and mutations seen across many myeloid neoplasms are nonspecific.
- `suspicious_for_other_pathology`: the variant is a strong, clinically meaningful molecular signal for a distinct disease entity or lineage and therefore warrants investigation for concurrent pathology, despite not changing the frozen primary WHO5 diagnosis. The variant does not need to prove a second neoplasm by itself. A recurrent hotspot described by the supplied WHO5 authority as a hallmark, defining molecular subset, diagnostic criterion, or useful discriminator/differential marker for a distinct lineage/entity may qualify. Do not use this classification for a weak or merely reported association.
- `other_pathology` must be null unless `classification` is `suspicious_for_other_pathology`; for that classification it must name the most specific distinct disease entity, disease family, or lineage-level pathology justified by the supplied WHO5 authority cards. Do not claim a narrower entity than the cards support.
- `variant_assessments[].reason` is one concise variant-level explanation of the diagnostic classification.

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
    classification: "<diagnostic_for_primary|nonspecific|suspicious_for_other_pathology>"
    other_pathology: null
    reason: "<one concise variant-level reason>"
```
