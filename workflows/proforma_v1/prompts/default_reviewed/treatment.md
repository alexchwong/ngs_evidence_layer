# Treatment implications

Using only the supplied case, authoritative diagnosis, and treatment cards, address every supplied variant in the authoritative disease. When no NGS variants are detected, return `classification: []`; do not create a pseudo-variant for a negative NGS result.

Reasoning feedback (null on first pass):
{{ input.reasoning_feedback }}

If feedback is supplied, correct only the identified clinical coherence/evidence-loss problem(s) and preserve unrelated valid decisions.

Preserve material restrictions from the supplied evidence when stating clinical rules or applying them to this patient. Do not broaden a rule by dropping or changing required allelic state, variant class, threshold, disease/subtype, therapy or exposure context, co-mutation/exclusion context, cytogenetic context, population, endpoint, framework/source attribution, polarity, uncertainty, or evidentiary strength.

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

Evidence assignment is downstream in this workflow. Do not choose or rank cards and do not emit evidence-card/card-tag bookkeeping fields.
