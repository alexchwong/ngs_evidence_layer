# Germline predisposition

Assess whether the NGS findings TOGETHER WITH the supplied clinical picture support a germline predisposition syndrome.

The clinical picture includes only information actually supplied in the case, such as age, personal history, family history, phenotype, and prior malignancies. Do not interpret an isolated molecular finding as sufficient clinical germline support unless the supplied evidence explicitly permits that conclusion.

- `ngs_no_variants_detected` means no SNV, short insertion/deletion, or short-range complex variant was detected in those genes within validated NGS assay scope; do not extend that negative result to copy-number changes, rearrangements, structural variants, or other unassayed variant classes.

Classify every supplied variant:
- `germline_support`: molecular finding plus clinical picture support consideration of a germline syndrome.
- `germline_against`: integrated molecular and clinical picture argue against a germline syndrome.
- `germline_uncertain`: available molecular/clinical information is insufficient for either conclusion.

`reason` must integrate molecular evidence and the supplied clinical context. Do not recommend testing, referral, or counselling.
Evidence assignment:
- For every reportable proposition you create, also return `evidence_card_tags` using only exact card IDs supplied to this owner step.
- Use an empty list when none of the supplied cards genuinely supports that proposition. Do not copy a merely related card.
- A card tag outside the supplied owner envelope is invalid and the complete owner artifact will be returned for repair.

