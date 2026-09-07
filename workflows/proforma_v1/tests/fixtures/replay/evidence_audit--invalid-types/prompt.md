# Fact-to-card evidence audit

The input is divided into independent JSON fact blocks named `<fact-1>...</fact-1>`, `<fact-2>...</fact-2>`, and so on.

Each block contains one clinical `fact` and ONLY the cards that the evidence matcher selected for that fact. Audit every supplied card independently against the fact in the SAME block. Do not infer, request, or audit any unmatched card.

For each supplied card answer one question:

- `card_is_element_of_reason`: does the card genuinely support one complete clinical proposition in the fact at that proposition's stated scope?

A card about a different clinical use of the same gene is not support. Topical relevance, a shared gene/disease, absence of contrary evidence, or merely compatible wording is insufficient.

Preserve material meaning. A card with a required restriction cannot support a broader proposition that drops or changes that restriction. Material restrictions include, where relevant, allelic state, variant class, threshold, disease/subtype, therapy or exposure context, co-mutation or exclusion context, cytogenetic context, population, endpoint, framework/source attribution, polarity, uncertainty, and evidentiary strength or modality. Ordinary paraphrase is acceptable when the clinical meaning and restrictions are unchanged.

If the fact is one atomic proposition, `card_is_element_of_reason` is true only when the card supports that complete proposition. If the fact genuinely contains multiple independent propositions, a card may support one complete proposition without supporting the others. Supporting only a fragment of one proposition is insufficient.

Use `risk: warning` only for a non-gating fidelity/context concern after complete proposition support is established. A material mismatch in restriction, scope, polarity, attribution, uncertainty, or evidentiary strength/modality is a failed card, not a warning. Use `comments: []` for an uncomplicated pass. For a failed card or a warning, give only a concise explanation of the mismatch or concern.

Return YAML only, preserving supplied evidence IDs, card IDs and order:
```yaml
audits:
  - evidence_id: E0001
    card_audits:
      - card_tag: "[card:0123456789ab]"
        card_is_element_of_reason: true
        risk: none
        comments: []
      - card_tag: "[card:abcdef012345]"
        card_is_element_of_reason: false
        risk: none
        comments:
          - "The card addresses treatment response, not the prognostic proposition stated in the fact."
```
