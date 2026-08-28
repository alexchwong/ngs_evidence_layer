# Germline predisposition

Assess whether the NGS findings TOGETHER WITH the supplied clinical picture raise sufficient suspicion for an inherited predisposition to warrant dedicated germline evaluation.

This step assesses whether germline evaluation is indicated; it does not establish whether a variant is constitutionally present. A `germline_suspicious` classification means germline predisposition is sufficiently suspected to justify confirmation, not that germline status has been proven.

The clinical picture includes only information actually supplied in the case, such as age, personal history, family history, phenotype, and prior malignancies. Do not interpret an isolated molecular finding as sufficient clinical germline suspicion unless the supplied evidence explicitly permits that conclusion.

- `ngs_no_variants_detected` means no SNV, short insertion/deletion, or short-range complex variant was detected in those genes within validated NGS assay scope; do not extend that negative result to copy-number changes, rearrangements, structural variants, or other unassayed variant classes.

Classify every supplied variant:
- `germline_suspicious`: the molecular finding plus supplied clinical picture are sufficiently compatible with a recognised inherited predisposition that dedicated germline evaluation is warranted.
- `germline_against`: the integrated molecular and clinical picture do not provide a reasonable indication for dedicated germline evaluation.
- `germline_uncertain`: the available molecular/clinical information is genuinely insufficient to decide whether dedicated germline evaluation is warranted.

Do not use `germline_uncertain` merely because constitutional testing, segregation analysis, family testing, genetic counselling, or prior referral has not occurred. Those are downstream investigations and may be absent precisely because this report is deciding whether germline evaluation should now be pursued.

`reason` must integrate molecular evidence and the supplied clinical context. For `germline_suspicious`, recommend dedicated germline evaluation with constitutional confirmation, without claiming confirmed germline status; genetic counselling or referral may also be recommended when supported by the supplied evidence.
Evidence assignment:
- For every reportable proposition you create, also return `evidence_card_tags` using only exact card IDs supplied to this owner step.
- Use an empty list when none of the supplied cards genuinely supports that proposition. Do not copy a merely related card.
- A card tag outside the supplied owner envelope is invalid and the complete owner artifact will be returned for repair.
