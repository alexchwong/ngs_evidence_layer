# ICC diagnostic evidence adjudication

For each disputed ICC diagnostic fact/card pair, decide only whether the supplied card is sufficient support for the proposed ICC diagnostic proposition.

Use only the supplied proposition, patient facts and disputed card. Require support for the relevant defining ICC criterion while preserving all material restrictions, including thresholds, exclusions, precedence/supersession, finite gene-set membership, allelic state, variant class, disease/subtype, co-mutation or cytogenetic context, and ICC classification scope.

Do not rewrite the diagnosis, introduce another card, or use evidence outside the disputed pair.

Copy each supplied `dispute_id` exactly. Return exactly one answer for every dispute ID.

Return YAML only:
```yaml
adjudications:
  - dispute_id: D0001
    decision: include
    reason: "<one concise reason>"
```
