# ICC molecular/cytogenetic diagnosis update

Use the structured case's provisional morphologic diagnosis as the starting diagnosis. Its provenance is supplied separately as `morphologic_diagnosis_origin`; do not change that provenance.

Using only the supplied ICC authority cards, decide whether the NGS findings and supplied cytogenetics refine, supersede, or leave unchanged the starting diagnosis under ICC.

The WHO5 diagnosis is supplied only as context. Do not alter it and do not write a separate WHO5/ICC comparison.

Rules:
- Return one ICC diagnosis only.
- `diagnostic_effect` must be exactly `unchanged`, `refined`, or `superseded` relative to the starting morphologic diagnosis.
- `variants` contains only variant IDs that materially contribute to the ICC diagnosis update; it may be empty.
- Use deterministic finite-gene-set membership supplied by core when present.
- `ngs_no_variants_detected` means no SNV, short insertion/deletion, or short-range complex variant was detected in those genes within validated NGS assay scope; do not extend that negative result to copy-number changes, rearrangements, structural variants, or other unassayed variant classes.
- Do not claim an unlisted variant satisfies a closed molecular criterion.
- `reason` is one concise patient-level proposition about the molecular/cytogenetic effect on diagnosis. Do not relitigate morphology.

Return YAML only:
```yaml
diagnosis: "<ICC diagnosis>"
diagnostic_effect: "<unchanged|refined|superseded>"
variants: [v01]
reason: "<one concise reason>"
```
