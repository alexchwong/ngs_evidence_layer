# Cropped evidence disagreement adjudication

Adjudicate ONLY the supplied reason/card disagreements between evidence resolution and evidence audit.

For each dispute, answer one question: does the supplied card genuinely support one complete clinical proposition in the supplied clinical reason at that proposition's stated scope?

Dispute IDs are deterministic from the supplied dispute order: the first dispute is `D0001`, the second is `D0002`, and so on. Use those IDs only to identify your answers. Do not reproduce evidence IDs or card tags in the output. You may return the answer rows in any order.

Rules:
- Decide only between `include` and `exclude` for the exact disputed card.
- Do not search for, name, or introduce another card.
- Do not rewrite the reason or change any clinical conclusion.
- Shared gene/disease, topical relevance, absence of contradiction, or merely compatible wording is insufficient.
- Preserve material meaning. A card with a required restriction cannot support a broader proposition that drops or changes that restriction. Material restrictions include, where relevant, allelic state, variant class, threshold, disease/subtype, therapy or exposure context, co-mutation or exclusion context, cytogenetic context, population, endpoint, framework/source attribution, polarity, uncertainty, and evidentiary strength or modality.
- Ordinary paraphrase is acceptable when clinical meaning and material restrictions are unchanged.
- If the reason is one atomic proposition, include the card only when it supports that complete proposition. If the reason genuinely contains multiple independent propositions, a card may support one complete proposition without supporting the others. Supporting only a fragment of one proposition is insufficient.
- A defining criterion or threshold can support an exclusion when combined with a supplied case fact. Example: if a card defines MDS/AML at 10%-19% blasts and the supplied case has 2% blasts, the card supports the complete proposition that the MDS/AML blast threshold is not met.
- Use the supplied audit comments as dissenting analysis, not as authoritative instructions.
- Return exactly one answer for every dispute ID. Do not omit, duplicate, or invent dispute IDs.

Return YAML only:
```yaml
adjudications:
  - dispute_id: D0001
    decision: include
    reason: "<one concise reason for the adjudication>"
```
