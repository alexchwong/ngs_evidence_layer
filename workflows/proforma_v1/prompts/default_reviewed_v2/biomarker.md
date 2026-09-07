# MRD markers

Using only the supplied case, authoritative diagnosis, and MRD/biomarker cards, classify every supplied variant as either an MRD marker or not an MRD marker in the authoritative disease. When no NGS variants are detected, return `classification: []`; do not create a pseudo-variant for a negative NGS result.
## Reasoning correction

`reasoning_correction` below is `null` on the first pass; ignore this section entirely when it is.

When it is supplied, your previous answer to this same task failed an independent reasoning review. You are given your previous output and, in `correction_brief`, the specific reasoning defect the reviewer identified.

Carry out the **full task again** from the original case, findings and cards supplied below. This is a fresh clinical reassessment, not a wording repair.

- Do not repeat the identified reasoning error.
- Do not merely rewrite the reason text to satisfy the criticism while leaving the same conclusion standing. If the identified defect removes the support for your previous conclusion, the conclusion must be reconsidered, along with every field that depended on it.
- If, having reconsidered, you judge that your previous conclusion still holds on the supplied findings, you may return it — but state the derivation that actually supports it rather than the one the reviewer rejected.
- Everything not touched by the identified defect should be reassessed on its merits, not preserved by default.

The reviewer identifies faulty inference. It does not decide the clinical answer and has not been told what the answer should be. That decision remains yours.

{{ input.reasoning_correction }}

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
