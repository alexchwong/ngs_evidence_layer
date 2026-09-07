# Treatment implications

Using only the supplied case, authoritative diagnosis, and treatment cards, address every supplied variant in the authoritative disease. When no NGS variants are detected, return `classification: []`; do not create a pseudo-variant for a negative NGS result.
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

Treatment categories:
- `drug_target`: the molecular lesion is directly targetable.
- `drug_sensitive`: the finding predicts increased sensitivity/response without itself being the direct target.
- `drug_resistant`: the finding predicts resistance or reduced response.
- `no_drug_implication`: no supported therapeutic implication in the supplied disease-specific evidence.
Rules:
- Every positive treatment claim must be supported by evidence explicitly applicable to the authoritative disease. Do not borrow treatment evidence from another disease merely because the same gene or variant is present.
- A card explicitly covering multiple diseases is usable when the authoritative disease is one of them.
- `ngs_no_variants_detected` means no SNV, short insertion/deletion, or short-range complex variant was detected in those genes within validated NGS assay scope; do not extend that negative result to copy-number changes, rearrangements, structural variants, or other unassayed variant classes.
- A variant may appear in more than one positive treatment category when the propositions are genuinely distinct.
- Give variants sharing one proposition the same `reason` wording; they are merged deterministically afterwards.
- A variant with any positive treatment implication must not appear in `no_drug_implication`.
- Keep reasons concise and evidence-backed.
Evidence assignment:
- For every reportable proposition you create, also return `evidence_card_tags` using only exact card IDs supplied to this owner step.
- Use an empty list when none of the supplied cards genuinely supports that proposition. Do not copy a merely related card.
- A card tag outside the supplied owner envelope is invalid and the complete owner artifact will be returned for repair.
