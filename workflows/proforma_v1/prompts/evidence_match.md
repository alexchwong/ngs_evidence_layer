# Batched fact-to-card evidence match

The input is divided into independent JSON fact blocks named `<fact-1>...</fact-1>`, `<fact-2>...</fact-2>`, and so on.

For EVERY supplied fact block, decide which cards inside THAT SAME block genuinely support a complete clinical proposition in the `fact`. Never use a card from another fact block. Every card available to a fact is rendered inside that fact's own JSON block and identified by its exact `card_id` in `[card:0123456789ab]` form.

A card supports a proposition only when the proposition expressed by the card entails that proposition at the fact's stated clinical scope. Topical relevance, a shared gene/disease, absence of contradiction, or merely compatible wording is insufficient.

Preserve material meaning. A card with a required restriction cannot support a broader proposition that drops or changes that restriction. Material restrictions include, where relevant, allelic state, variant class, threshold, disease/subtype, therapy or exposure context, co-mutation or exclusion context, cytogenetic context, population, endpoint, framework/source attribution, polarity, uncertainty, and evidentiary strength or modality. Ordinary paraphrase is acceptable when the clinical meaning and restrictions are unchanged.

If the fact is one atomic proposition, a selected card must support that complete proposition. If the fact genuinely contains multiple independent propositions, different cards may support different complete propositions within it; no card needs to support unrelated propositions in the same compound fact. Supporting only a fragment of one proposition is insufficient.

If none of the cards in a fact block supports a complete proposition in that fact, return an empty `card_tags` list. Do not choose a merely related, narrower, differently scoped, or weaker card.

Later match passes, when configured, contain only facts that received zero cards on the preceding pass. Reconsider those supplied cards independently; do not infer facts or cards that are absent from the current pass.

Do not rewrite, broaden, narrow, or reinterpret the fact to fit a card.

Return YAML only, preserving supplied evidence IDs and order:
```yaml
matches:
  - evidence_id: E0001
    card_tags:
      - "exact supplied [card:0123456789ab] tag"
      - "exact supplied [card:abcdef012345] tag"
  - evidence_id: E0002
    card_tags: []
```
