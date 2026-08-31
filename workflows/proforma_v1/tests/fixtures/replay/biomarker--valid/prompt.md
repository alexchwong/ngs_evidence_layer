# MRD markers

Using only the supplied case, authoritative diagnosis, and MRD/biomarker cards, classify every supplied variant as either an MRD marker or not an MRD marker in the authoritative disease.

Rules:
- Every positive MRD/biomarker claim must be supported by evidence explicitly applicable to the authoritative disease. Do not borrow biomarker evidence from another disease merely because the same gene or variant is present.
- A card explicitly covering multiple diseases is usable when the authoritative disease is one of them.
- `ngs_no_variants_detected` means no SNV, short insertion/deletion, or short-range complex variant was detected in those genes within validated NGS assay scope; do not extend that negative result to copy-number changes, rearrangements, structural variants, or other unassayed variant classes.
- Give variants sharing one proposition the same `reason` wording; they are merged deterministically afterwards.
- `reason` is one concise evidence-backed proposition.
- Do not recommend a marker unless the supplied evidence supports its use for MRD in the authoritative disease.
Evidence assignment:
- For every reportable proposition you create, also return `evidence_card_tags` using only exact card IDs supplied to this owner step.
- Use an empty list when none of the supplied cards genuinely supports that proposition. Do not copy a merely related card.
- A card tag outside the supplied owner envelope is invalid and the complete owner artifact will be returned for repair.
