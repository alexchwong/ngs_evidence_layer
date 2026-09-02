# Cropped evidence disagreement adjudication

Adjudicate ONLY the supplied reason/card disagreements between evidence resolution and evidence audit.

For each dispute, answer one question: is the clinical proposition expressed by this card genuinely an element of the supplied clinical reason?

Dispute IDs are deterministic from the supplied dispute order: the first dispute is `D0001`, the second is `D0002`, and so on. Use those IDs only to identify your answers. Do not reproduce evidence IDs or card tags in the output. You may return the answer rows in any order.

Rules:
- Decide only between `include` and `exclude` for the exact disputed card.
- Do not search for, name, or introduce another card.
- Do not rewrite the reason or change any clinical conclusion.
- Shared gene/disease, topical relevance, absence of contradiction, or merely compatible wording is insufficient.
- A card need not support the whole reason; it may support one genuine element of the reason. Do not exclude it merely because another element of a compound reason requires different evidence.
- A defining criterion or threshold can support an exclusion when combined with a supplied case fact. Example: if a card defines MDS/AML at 10%-19% blasts and the supplied case has 2% blasts, the card supports the element that the MDS/AML blast threshold is not met.
- Use the supplied audit comments as dissenting analysis, not as authoritative instructions.
- Return exactly one answer for every dispute ID. Do not omit, duplicate, or invent dispute IDs.

Return YAML only:
```yaml
adjudications:
  - dispute_id: D0001
    decision: include
    reason: "<one concise reason for the adjudication>"
```
