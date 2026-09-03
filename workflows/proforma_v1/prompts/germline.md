# Germline predisposition

Assess whether each supplied NGS molecular finding, together with the supplied clinical picture and the supplied germline evidence cards, raises sufficient suspicion for an inherited predisposition to warrant dedicated germline evaluation. When no NGS molecular findings are supplied, return `classification: []`; do not create a pseudo-variant for a negative NGS result.

This step assesses whether germline evaluation is indicated; it does not establish whether a molecular finding is constitutionally present. A `germline_suspicious` classification means germline predisposition is sufficiently suspected to justify confirmation, not that germline status has been proven.

## Eligibility

Determine eligibility separately for every supplied molecular finding before completing detailed germline reasoning.

- Use `eligibility: assess` only when at least one supplied germline evidence card genuinely establishes an inherited-predisposition association relevant to that finding's gene and molecular mechanism.
- Use `eligibility: skip_no_predisposition_evidence` when the supplied germline evidence cards do not establish such an association.
- Eligibility is corpus-bounded. Do not use pretrained knowledge, familiarity with a gene, or the existence of a non-germline evidence card to create germline eligibility.
- A skipped finding receives no detailed germline worksheet and no germline bucket. Follow the output contract exactly for skipped rows.

## Detailed germline proforma

For every finding with `eligibility: assess`, complete every reasoning field before assigning the integrated germline bucket.

Assess these factors independently:
- `predisposition_evidence`: state the inherited-predisposition mechanism supported by the supplied germline evidence and copy only exact supporting owner card tags supplied to this step;
- `event_compatibility`: whether the observed molecular event type and reported finding are compatible with the inherited mechanism supported by the supplied evidence;
- `age`: the relationship between the supplied patient age and the predisposition evidence;
- `vaf`: the relationship between the supplied VAF and the possibility of constitutional versus acquired origin, to the extent supported by the supplied evidence and case context;
- `personal_history`: whether the supplied personal history changes germline suspicion;
- `family_history`: whether the supplied family history changes germline suspicion;
- `phenotype`: whether the supplied phenotype or syndromic/clinical features change germline suspicion.

For `event_compatibility`, `age`, `vaf`, `personal_history`, `family_history`, and `phenotype`, classify the direction of the factor's effect on germline suspicion using exactly one status:
- `supportive`: the supplied factor increases suspicion for inherited predisposition;
- `consistent`: the supplied factor is compatible with inherited predisposition and is neutral with respect to suspicion; it neither increases nor decreases suspicion;
- `discordant`: the supplied factor weighs against inherited predisposition, even when inherited predisposition remains possible;
- `not_supplied`: the relevant information was not supplied in the case;
- `not_assessable`: the relevant information was supplied, but the supplied evidence and case context do not permit its germline significance to be assessed.

The categorical `status` must agree with the accompanying `reason`. If the reason says a feature is atypical, unusual, later or earlier than expected, less characteristic, or otherwise weighs against inherited predisposition, use `discordant` unless the supplied evidence establishes that the feature is expected and does not weigh against germline suspicion. Do not use `consistent` merely because inherited predisposition remains possible.

Do not treat missing information as supportive or consistent. Do not convert `not_supplied` into an assumed negative history. Do not use a universal age or VAF threshold. A discordant factor weighs against germline suspicion but is not an automatic exclusion; integrate all completed factors and the supplied evidence.

A recognised predisposition association for the gene alone is not sufficient for `germline_suspicious`. The integrated conclusion must consider the actual reported molecular event and all supplied clinical context.

`predisposition_evidence` and `event_compatibility` establish whether germline predisposition is relevant and biologically possible. They do not, by themselves, establish that the observed finding is likely to be constitutional.

## Integrated classification

Assign the final bucket only after assessing all supplied factors.

- `germline_suspicious`
  - Use when the overall patient-specific evidence positively supports constitutional origin.
  - Known germline predisposition for the gene and compatibility of the observed event are necessary context, but are not sufficient on their own.
  - `consistent`, `not_supplied`, and `not_assessable` factors are neutral.
  - Discordant factors must weigh against this bucket.
  - Do not use this bucket merely because germline origin remains possible or cannot be excluded.

- `germline_against`
  - Use when the overall patient-specific evidence weighs against constitutional origin.
  - Germline origin does not need to be impossible or excluded.

- `germline_uncertain`
  - Use when the supplied evidence does not give a clear overall direction.
  - This may include competing supportive and discordant factors or important factors that cannot be interpreted.

Do not use `germline_uncertain` merely because constitutional testing, segregation analysis, family testing, genetic counselling, or prior referral has not occurred. Those are downstream investigations and may be absent precisely because this report is deciding whether germline evaluation should now be pursued.

The final `reason` must:
- identify the most important supportive, neutral, discordant, and unavailable factors;
- state which direction the evidence overall supports;
- explain why that direction justifies the selected bucket;
- where relevant, recommend correlation with missing clinical or family information without treating missing information as supportive evidence.

For `germline_suspicious`, recommend dedicated germline evaluation with constitutional confirmation without claiming confirmed germline status; genetic counselling or referral may also be recommended when supported by the supplied evidence.

Evidence assignment:
- For every evidence assignment, use only exact owner card tags supplied in this step.
- Copy each supplied card tag verbatim, including its complete `[card:...]` wrapper. Never return the bare internal card identifier.
- Apply this rule both to `predisposition_evidence.evidence_card_tags` and to the final `evidence_card_tags`.
- Use an empty list where the output contract permits it and no supplied card genuinely supports the proposition. Do not copy a merely related card.
- A tag that is not an exact member of the supplied owner-card envelope is invalid.
