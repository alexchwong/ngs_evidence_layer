# WHO1 routing evidence adjudication

For each disputed WHO1 routing fact/card pair, decide only whether the supplied card is sufficient support for the routing-changing diagnostic proposition under the diagnosis-complete-support policy.

Consider defining criteria, thresholds, exclusions, precedence/supersession, finite gene-set membership, schema disease and routing consequence where applicable. Do not rewrite the diagnosis, introduce another card, or select evidence outside the disputed pair.

Preserve the supplied evidence ID, card tag, and order exactly. Decide only `include` or `exclude`.

Return YAML only in this exact shape:
```yaml
adjudications:
  - evidence_id: EWHO1
    card_tag: "[card:0123456789ab]"
    decision: include
    reason: "<one concise reason for the adjudication>"
```
