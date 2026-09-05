# WHO1 diagnostic evidence audit

Independently audit each supplied WHO1 diagnostic fact/card pair. The fact contains the proposed WHO5 diagnosis, diagnostic effect, supporting rationale, starting morphologic diagnosis, and relevant case facts. The card must genuinely support the relevant defining diagnostic criterion as applied to those facts, not merely be related to the disease or gene.

Assess defining criteria, required thresholds, exclusions, precedence/supersession, finite gene-set membership, schema disease and derived routing consequence where applicable. Mark `card_is_element_of_reason: true` only when the card supports the complete proposed diagnostic proposition represented by the fact.

Return exactly one audit for every supplied card and no others. Preserve the supplied evidence ID, card tag, and order exactly.

Return YAML only in this exact shape:
```yaml
audits:
  - evidence_id: EWHO1
    card_audits:
      - card_tag: "[card:0123456789ab]"
        card_is_element_of_reason: true
        risk: none
        comments: []
```

Use `risk: warning` only for a non-gating fidelity/strength/context concern when the card still supports the diagnostic proposition. For a failed card or warning, use `comments` only for a concise explanation of the mismatch or concern.
