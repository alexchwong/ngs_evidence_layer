# MRD markers

Using only the supplied case, diagnosis, and MRD/biomarker cards, classify every supplied variant as either an MRD marker or not an MRD marker in the current disease context.

Rules:
- `ngs_no_variants_detected` means no SNV, short insertion/deletion, or short-range complex variant was detected in those genes within validated NGS assay scope; do not extend that negative result to copy-number changes, rearrangements, structural variants, or other unassayed variant classes.
- Give variants sharing one proposition the same `reason` wording; they are merged deterministically afterwards.
- `reason` is one concise evidence-backed proposition.
- Do not recommend a marker unless the supplied evidence supports its use for MRD in the current context.
