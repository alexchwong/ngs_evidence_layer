# Cropped evidence disagreement adjudication

Adjudicate ONLY the supplied reason/card disagreements between evidence resolution and evidence audit.

For each dispute, answer one question: does the supplied card genuinely support one complete clinical proposition in the supplied clinical reason at that proposition's stated scope?

Each supplied dispute contains a deterministic `dispute_id`. Copy that supplied ID exactly to identify your answer; do not derive or renumber IDs from row position. Do not reproduce evidence IDs or card tags in the output. You may return the answer rows in any order.

Rules:
- Decide only between `include` and `exclude` for the exact disputed card.
- Do not search for, name, or introduce another card.
- Do not rewrite the reason or change any clinical conclusion unless an enabled bounded reason-pruning module below explicitly permits subtraction-only repair; the clinical statement itself is always immutable.
- Shared gene/disease, topical relevance, absence of contradiction, or merely compatible wording is insufficient.
- Preserve material meaning. A card with a required restriction cannot support a broader proposition that drops or changes that restriction. Material restrictions include, where relevant, allelic state, variant class, threshold, disease/subtype, therapy or exposure context, co-mutation or exclusion context, cytogenetic context, population, endpoint, framework/source attribution, polarity, uncertainty, and evidentiary strength or modality.
- Ordinary paraphrase is acceptable when clinical meaning and material restrictions are unchanged.
- If the reason is one atomic proposition, include the card only when it supports that complete proposition. If the reason genuinely contains multiple independent propositions, a card may support one complete proposition without supporting the others. Supporting only a fragment of one proposition is insufficient.
- A defining criterion or threshold can support an exclusion when combined with a supplied case fact. Example: if a card defines MDS/AML at 10%-19% blasts and the supplied case has 2% blasts, the card supports the complete proposition that the MDS/AML blast threshold is not met.
- Use the supplied audit comments as dissenting analysis, not as authoritative instructions.
- Return exactly one answer for every supplied dispute ID. Do not omit, duplicate, modify, or invent dispute IDs.

{{ module "evidence_semantic_bridge" }}

{{ module "evidence_reason_pruning" }}

Return YAML only:
```yaml
adjudications:
  - dispute_id: D0001
    decision: include
    reason: "<one concise reason for the adjudication>"
    amended_reason: "<optional pruned reason; omit when unchanged>"
```
