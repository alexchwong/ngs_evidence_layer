# ICC diagnostic evidence audit

Independently audit every supplied ICC diagnostic fact/card pair. Each `<fact-N>...</fact-N>` block is isolated; assess only the fact and cards inside that block.

A card passes only when it genuinely supports the complete ICC diagnostic proposition at the stated patient-specific scope, not merely because it is related to the same disease or gene.

Assess defining criteria, thresholds, exclusions, precedence/supersession, finite gene-set membership, allelic state, variant class, disease/subtype, co-mutation or cytogenetic context, and ICC-specific classification scope where applicable. A narrower or differently scoped card does not support a broader proposition that drops a material restriction.

Return exactly one audit for every supplied card and no others. Preserve evidence IDs, card tags and order exactly.

Return YAML only:
```yaml
audits:
  - evidence_id: EICC
    card_audits:
      - card_tag: "[card:0123456789ab]"
        card_is_element_of_reason: true
        risk: none
        comments: []
```

Use `risk: warning` only for a non-gating fidelity/context concern after sufficient support is established. Material mismatch is a failed card, not a warning.
