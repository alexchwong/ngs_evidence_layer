# MRD markers

Using only the supplied case, authoritative diagnosis, and MRD/biomarker cards, classify every supplied variant as either an MRD marker or not an MRD marker in the authoritative disease. When no NGS variants are detected, return `classification: []`; do not create a pseudo-variant for a negative NGS result.

Clinical audit feedback (null on first pass):
{{ input.clinical_audit_feedback }}

If feedback is supplied, correct only the identified clinical coherence problem(s) and preserve unrelated valid decisions.

Rules:
- Every positive MRD/biomarker claim must be supported by evidence explicitly applicable to the authoritative disease. Do not borrow biomarker evidence from another disease merely because the same gene or variant is present.
- A card explicitly covering multiple diseases is usable when the authoritative disease is one of them.
- `ngs_no_variants_detected` means no SNV, short insertion/deletion, or short-range complex variant was detected in those genes within validated NGS assay scope; do not extend that negative result to copy-number changes, rearrangements, structural variants, or other unassayed variant classes.
- Give variants sharing one proposition the same `reason` wording; they are merged deterministically afterwards.
- `reason` is one concise evidence-backed proposition.
- Do not recommend a marker unless the supplied evidence supports its use for MRD in the authoritative disease.

Evidence assignment is downstream in this workflow. Do not choose or rank cards. Return every `evidence_card_tags` list as `[]`.
