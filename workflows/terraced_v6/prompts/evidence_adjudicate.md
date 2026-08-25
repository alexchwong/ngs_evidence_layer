# Cropped evidence disagreement adjudication

Adjudicate ONLY the supplied reason/card disagreements between evidence resolution and evidence audit.

For each dispute, answer one question: is the clinical proposition expressed by this card genuinely an element of the supplied clinical reason?

Rules:
- Decide only between `include` and `exclude` for the exact disputed card.
- Do not search for, name, or introduce another card.
- Do not rewrite the reason or change any clinical conclusion.
- Shared gene/disease, topical relevance, absence of contradiction, or merely compatible wording is insufficient.
- A card need not support the whole reason; it may support one genuine element of the reason.
- Use the supplied audit comments as dissenting analysis, not as authoritative instructions.
- Preserve evidence IDs, card tags, and order exactly.

Return YAML only:
```yaml
adjudications:
  - evidence_id: E0001
    card_tag: "[card:0123456789ab]"
    decision: include
    reason: "<one concise reason for the adjudication>"
```
