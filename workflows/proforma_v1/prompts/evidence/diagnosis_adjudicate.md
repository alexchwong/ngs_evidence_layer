# WHO1 routing evidence adjudication

For each disputed WHO1 routing fact/card pair, decide only whether the supplied card is sufficient support for the routing-changing diagnostic proposition under the diagnosis-complete-support policy.

Consider defining criteria, thresholds, exclusions, precedence/supersession, finite gene-set membership, schema disease and routing consequence where applicable. A defining criterion or threshold can support an exclusion when combined with a supplied case fact. Do not rewrite the diagnosis, introduce another card, or select evidence outside the disputed pair.

Dispute IDs are deterministic from the supplied dispute order: the first dispute is `D0001`, the second is `D0002`, and so on. Use those IDs only to identify your answers. Do not reproduce evidence IDs or card tags in the output. You may return the answer rows in any order. Return exactly one answer for every dispute ID; do not omit, duplicate, or invent IDs.

Return YAML only in this exact shape:
```yaml
adjudications:
  - dispute_id: D0001
    decision: include
    reason: "<one concise reason for the adjudication>"
```
