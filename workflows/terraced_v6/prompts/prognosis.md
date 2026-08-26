# Prognosis

Using only the supplied case, diagnosis, and prognosis cards, classify every supplied variant once by its principal supported prognostic effect in the current disease context.

Rules:
- `ngs_no_variants_detected` means no SNV, short insertion/deletion, or short-range complex variant was detected in those genes within validated NGS assay scope; do not extend that negative result to copy-number changes, rearrangements, structural variants, or other unassayed variant classes.
- `reason` is one concise report-ready clinical proposition. Give variants sharing one proposition the same `reason` wording; they are merged deterministically afterwards.
- Preserve qualitative strength from the evidence; do not weaken or strengthen it.
- Do not infer that one variant cancels another unless the supplied evidence explicitly defines that interaction.
- `prognostic_score` is populated only when this workflow can actually assign the named score/risk group from supplied information. Otherwise use null. Never say a score is "not calculable".
