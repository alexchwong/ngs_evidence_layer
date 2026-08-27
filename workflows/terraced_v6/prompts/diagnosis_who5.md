# WHO5 molecular/cytogenetic diagnosis update

Use the structured case's provisional morphologic diagnosis as the starting diagnosis. Its provenance is supplied separately as `morphologic_diagnosis_origin`; do not change that provenance.

Using only the supplied WHO5 authority cards, decide whether the NGS findings and supplied cytogenetics refine, supersede, or leave unchanged the starting diagnosis.

Rules:
- Return one WHO5 diagnosis only.
- Use one exact supplied `schema_disease` for deterministic routing.
- `diagnostic_effect` must be exactly `unchanged`, `refined`, or `superseded` relative to the starting morphologic diagnosis.
- `variants` contains only variant IDs that materially contribute to the WHO5 diagnosis update; it may be empty.
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
```
