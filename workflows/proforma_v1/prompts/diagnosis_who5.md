# WHO5 molecular/cytogenetic diagnosis update

Use the structured case's provisional morphologic diagnosis as the starting diagnosis. Its provenance is supplied separately as `morphologic_diagnosis_origin`; do not change that provenance.

Using only the supplied WHO5 authority cards, decide whether the NGS findings and supplied cytogenetic or other molecular findings refine, supersede, or leave unchanged the starting diagnosis.
Rules:
- First determine the WHO5 diagnosis exactly as before: return one WHO5 diagnosis, one exact supplied `schema_disease`, the `diagnostic_effect`, the diagnosis-contributing `variants`, and one concise `reason`.
- Complete and freeze that primary WHO5 decision before performing the variant assessments below. The variant assessments must not change `schema_disease`, `diagnosis`, `diagnostic_effect`, `variants`, or `reason`.
- Use one exact supplied `schema_disease` for deterministic routing.
- `diagnostic_effect` must be exactly `unchanged`, `refined`, or `superseded` relative to the starting morphologic diagnosis.
- `variants` contains only variant IDs that materially contribute to the WHO5 diagnosis update; it may be empty. Preserve this field's existing meaning; do not expand it merely because every variant is assessed below.
- A negative NGS result does not invalidate a supplied morphologic diagnosis. When no NGS variants are detected and no supplied cytogenetic or other molecular abnormality changes the diagnosis, retain the supplied morphologic diagnosis unchanged.
- Treat supplied cytogenetic, FISH, rearrangement, copy-number, PCR, and other non-NGS molecular abnormalities independently of NGS variant status. When such an abnormality is diagnostically defining or refining under WHO5, integrate it into the diagnosis even when `variants` is empty.
- When no morphologic diagnosis was supplied (`morphologic_diagnosis_origin: inferred`), no NGS variants are detected, and supplied cytogenetic/other molecular findings are absent, normal, or non-diagnostic, do not manufacture a definitive myeloid neoplasm from nonspecific findings alone. The diagnosis/reason must state that the supplied result does not exclude a myeloid neoplasm and that clinical/morphologic correlation is required.
- After the final primary WHO5 diagnosis is frozen, classify every detected variant exactly once in `variant_assessments`, relative to that final WHO5 diagnosis. When there are no detected variants, return `variant_assessments: []`.
  - `diagnostic_for_primary`: the variant is diagnostic/disease-defining for the final primary WHO5 disease. A variant that promotes or supersedes the starting morphology into the final WHO5 disease belongs here, not under another pathology.
  - `nonspecific`: the variant does not provide a sufficiently strong diagnostic signal for either the final primary WHO5 disease or a distinct other pathology. Common cross-disease mutations, broad associations, prognostic-only findings, and mutations seen across many myeloid neoplasms are nonspecific.
  - `diagnostic_for_other_pathology`: the variant is a strong, clinically meaningful molecular signal for a distinct disease entity or lineage and therefore warrants investigation for concurrent pathology, despite not changing the frozen primary WHO5 diagnosis. The variant does not need to prove a second neoplasm by itself.
A recurrent hotspot described by the supplied WHO5 authority as a hallmark, defining molecular subset, or useful discriminator/differential marker for a distinct lineage/entity may qualify. Do not use this classification for a weak or merely reported association.
- `other_pathology` must be null unless `classification` is `diagnostic_for_other_pathology`; for that classification it must name the most specific distinct disease entity, disease family, or lineage-level pathology justified by the supplied WHO5 authority cards. Do not claim a narrower entity than the cards support.
- `variant_assessments[].reason` is one concise variant-level explanation of the diagnostic classification.
- Use deterministic finite-gene-set membership supplied by core when present.
- `ngs_no_variants_detected` means no SNV, short insertion/deletion, or short-range complex variant was detected in those genes within validated NGS assay scope; do not extend that negative result to copy-number changes, rearrangements, structural variants, or other unassayed variant classes.
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
