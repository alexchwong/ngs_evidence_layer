# WHO5 molecular/cytogenetic diagnosis update

Use the structured case's `diagnosis_status` to determine how to interpret the starting disease context. Legacy cases without this field are treated as `new`.
- For `new`, use the structured case's provisional morphologic diagnosis as the starting diagnosis and apply the existing de-novo diagnostic update logic below.
- For `progress`, the structured case's `provisional_disease` is the established underlying disease context. The current specimen assesses response, persistence, progression, or transformation; it is not a de-novo opportunity to downgrade the established disease.
Its provenance is supplied separately as `morphologic_diagnosis_origin`; do not change that provenance.

Using only the supplied WHO5 authority cards, decide whether the NGS findings and supplied cytogenetic or other molecular findings refine, supersede, or leave unchanged the starting diagnosis.
Rules:
- First determine the WHO5 diagnosis exactly as before: return one WHO5 diagnosis, one exact supplied `schema_disease`, the `diagnostic_effect`, the diagnosis-contributing `variants`, and one concise `reason`.
- Complete and freeze that primary WHO5 decision before performing the variant assessments below. The variant assessments must not change `schema_disease`, `diagnosis`, `diagnostic_effect`, `variants`, or `reason`.
- Use one exact supplied `schema_disease` for deterministic routing.
- `diagnostic_effect` must be exactly `unchanged`, `refined`, or `superseded` relative to the starting morphologic diagnosis.
- `variants` contains only variant IDs that materially contribute to the WHO5 diagnosis update; it may be empty. Preserve this field's existing meaning; do not expand it merely because every variant is assessed below.
- A negative NGS result does not invalidate a supplied morphologic diagnosis. When no NGS variants are detected and no supplied cytogenetic or other molecular abnormality changes the diagnosis, retain the supplied morphologic diagnosis unchanged.
- For `diagnosis_status: progress`, treatment response must not downgrade the established disease entity. Reduced blasts, morphologic remission, improved counts, or disappearance/non-detection of a previously diagnostic molecular abnormality after therapy describe current disease/response status; they do not convert AML to MDS, MDS to CCUS, an established neoplasm to `no_haematological_malignancy`, or otherwise move the disease backwards to a lesser entity. Retain the established disease and describe the current treated/response state concisely in `reason`.
- For `diagnosis_status: progress`, negative NGS — including loss of a previously detected disease-defining variant — is a current molecular response/MRD observation and must not be used to retrospectively criticize or invalidate the established diagnosis.
- `progress` protects against treatment-related downgrading; it does not freeze the established disease label at its original level of specificity. Classify the underlying disease using all supplied disease-defining information that remains valid for classification, whether documented at the original diagnosis or in the current specimen. Historical diagnostic molecular/cytogenetic findings may therefore refine the established disease even when they are no longer detected after therapy; for example, established AML may be refined to AML-MR when supplied diagnostic-phase findings meet the relevant criteria.
- `progress` also does not block genuine progression or transformation. Current findings may supersede, up-stage, or transform the established disease when the supplied classification authority supports that change; for example, a prior MPN with a current blast percentage meeting blast-phase criteria may be classified as blast-phase/transformed disease.
- Treat supplied cytogenetic, FISH, rearrangement, copy-number, PCR, and other non-NGS molecular abnormalities independently of NGS variant status. When such an abnormality is diagnostically defining or refining under WHO5, integrate it into the diagnosis even when `variants` is empty.
- For `diagnosis_status: new`, when no morphologic diagnosis was supplied (`morphologic_diagnosis_origin: inferred`), no NGS variants are detected, and no supplied cytogenetic/other molecular finding currently establishes or refines a diagnosis — including when those studies are absent, normal, pending, unavailable, not performed, or otherwise non-diagnostic — do not manufacture a myeloid neoplasm from descriptive marrow findings or cytopenias. Return `schema_disease: no_haematological_malignancy`, `diagnosis: "No myeloid neoplasm established from supplied findings"`, `diagnostic_effect: unchanged`, `variants: []`, and `variant_assessments: []`. The `schema_disease` value in this branch is an internal routing sentinel only; it does not mean a myeloid neoplasm has been excluded. The `reason` must state that the result does not exclude a myeloid neoplasm, that clinical/morphologic correlation is required, and that any explicitly pending diagnostic study remains pending.
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
