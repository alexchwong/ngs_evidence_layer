# WHO1 routing evidence assignment

For each supplied `<fact-N>...</fact-N>` JSON block, select only cards that directly support the complete routing-changing WHO5 proposition for this patient.

A qualifying card must support the defining diagnostic criterion relevant to the proposed WHO5 diagnosis/routing change. Shared disease, gene, topic, or non-contradiction alone is insufficient. Where the proposition depends on a threshold, exclusion, precedence/supersession rule, finite gene set, or schema-disease consequence, the available card must genuinely support that criterion.

Return only exact card IDs supplied inside that fact block. If no supplied card adequately supports the complete proposition, return an empty list.

Return YAML only:
```yaml
matches:
  - evidence_id: EWHO1
    card_tags: ["[card:0123456789ab]"]
```
