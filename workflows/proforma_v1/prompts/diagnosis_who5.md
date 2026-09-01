# WHO5 molecular/cytogenetic diagnosis update

Use the structured case's `diagnosis_status` to determine how to interpret the starting disease context. Legacy cases without this field are treated as `new`.
- For `new`, use the structured case's provisional morphologic diagnosis as the starting diagnosis and apply the existing de-novo diagnostic update logic below.
- For `progress`, the structured case's `provisional_disease` is the established underlying disease context. The current specimen assesses response, persistence, progression, or transformation; it is not a de-novo opportunity to downgrade the established disease.
Its provenance is supplied separately as `morphologic_diagnosis_origin`; do not change that provenance.

Using only the supplied WHO5 authority cards, decide whether the NGS findings and supplied cytogenetic or other molecular findings refine, supersede, or leave unchanged the starting diagnosis.
Rules:
- For each detected variant, first assess its effect on the starting primary disease using all relevant supplied cards. Multiple cards may form an evidence chain, but every link from the finding through any intermediate state to the WHO5 entity must be supported by supplied cards. Do not consider concurrent pathology yet.
- For `diagnosis_status: progress`, determine the underlying disease classification before interpreting current response. Remission, reduced blasts, count recovery, or loss/non-detection of a previously diagnostic abnormality must not be used to reject historical molecular/cytogenetic subclassification.
- Then combine the variant-specific conclusions with applicable disease-level hierarchy, morphology, cytogenetics, and other molecular findings to determine the most specific underlying WHO5 diagnosis.
- After the underlying diagnosis is fixed, interpret current response, persistence, progression, or transformation. Response must not downgrade the established disease; supported current findings may up-stage or transform it.
- Use one exact supplied `schema_disease` for deterministic routing.
- `diagnostic_effect` must be exactly `unchanged`, `refined`, or `superseded` relative to the starting morphologic diagnosis.
- `variants` contains only variant IDs that materially contribute to the WHO5 diagnosis update; it may be empty.
- A negative NGS result does not invalidate a supplied morphologic diagnosis. When no NGS variants are detected and no supplied cytogenetic or other molecular abnormality changes the diagnosis, retain the supplied morphologic diagnosis unchanged.
- Treat supplied cytogenetic, FISH, rearrangement, copy-number, PCR, and other non-NGS molecular abnormalities independently of NGS variant status. When such an abnormality is diagnostically defining or refining under WHO5, integrate it into the diagnosis even when `variants` is empty.
- For `diagnosis_status: new`, when no morphologic diagnosis was supplied (`morphologic_diagnosis_origin: inferred`), no NGS variants are detected, and no supplied cytogenetic/other molecular finding currently establishes or refines a diagnosis — including when those studies are absent, normal, pending, unavailable, not performed, or otherwise non-diagnostic — do not manufacture a myeloid neoplasm from descriptive marrow findings or cytopenias. Return `schema_disease: no_haematological_malignancy`, `diagnosis: "No myeloid neoplasm established from supplied findings"`, `diagnostic_effect: unchanged`, `variants: []`, and `variant_assessments: []`. The `schema_disease` value in this branch is an internal routing sentinel only; it does not mean a myeloid neoplasm has been excluded. The `reason` must state that the result does not exclude a myeloid neoplasm, that clinical/morphologic correlation is required, and that any explicitly pending diagnostic study remains pending.
- After the primary WHO5 diagnosis is fixed, classify every detected variant exactly once in `variant_assessments` relative to that final diagnosis. When there are no detected variants, return `variant_assessments: []`.
  - `diagnostic_for_primary`: the variant contributed to defining or refining the final primary WHO5 disease.
  - `nonspecific`: the variant does not provide a sufficiently strong diagnostic signal for the final primary disease or a distinct other pathology.
  - `diagnostic_for_other_pathology`: consider only variants that did not contribute to the primary diagnosis; use only when supplied cards support a distinct pathology and do not show the variant as expected, defining, or refining in the final primary diagnosis. Mere occurrence in another disease is insufficient.
- `other_pathology` must be null unless `classification` is `diagnostic_for_other_pathology`; for that classification it must name the most specific distinct disease entity, disease family, or lineage-level pathology justified by the supplied WHO5 authority cards.
- `variant_assessments[].reason` is one concise variant-level explanation of the diagnostic classification.
- Use deterministic finite-gene-set membership supplied by core when present.
- `genes_without_detected_ngs_variants` lists genes without detected SNV, short insertion/deletion, or short-range complex variants within validated NGS assay scope; do not extend that result to copy-number changes, rearrangements, structural variants, or other unassayed variant classes.
- Do not claim an unlisted variant satisfies a closed molecular criterion.
- `reason` is one concise patient-level proposition about the molecular/cytogenetic effect on diagnosis. Do not relitigate morphology.
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
