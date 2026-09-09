# ICC diagnostic evidence assignment

For each supplied `<fact-N>...</fact-N>` JSON block, select only cards that directly support the complete proposed ICC diagnostic proposition for this patient.

Each fact is isolated. Use only cards inside the same fact block. Shared disease, gene, topic, or non-contradiction alone is insufficient. A qualifying card must support the defining ICC diagnostic criterion relevant to the proposition as applied to the supplied patient facts and rationale.

Preserve material restrictions, including where relevant threshold, exclusion, precedence/supersession rule, finite gene set, allelic state, variant class, disease/subtype, co-mutation or cytogenetic context, and classification-system scope. Ordinary paraphrase is acceptable only when meaning and restrictions are unchanged.

If no supplied card adequately supports the proposition, return an empty list. Do not rewrite or reinterpret the proposition to fit a card.

Return YAML only, preserving supplied evidence IDs and order:
```yaml
matches:
  - evidence_id: EICC
    card_tags: ["[card:0123456789ab]"]
```
