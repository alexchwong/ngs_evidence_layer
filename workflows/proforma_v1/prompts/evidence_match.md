# Batched fact-to-card evidence match

The input is divided into independent JSON fact blocks named `<fact-1>...</fact-1>`, `<fact-2>...</fact-2>`, and so on.

For EVERY supplied fact block, decide which cards inside THAT SAME block are genuine elements of the clinical `fact`. Never use a card from another fact block. Every card available to a fact is rendered inside that fact's own JSON block and identified by its exact `card_id` in `[card:0123456789ab]` form.

A card is an element of a fact only when the clinical proposition expressed by the card is actually present in that fact. Topical relevance, a shared gene/disease, or absence of contradiction is insufficient.

Select ALL cards in the block that independently match an element of the fact. More than one card may be selected. Do not require one card to support the whole fact: different cards may support different elements.

If none of the cards in a fact block is an element of that fact, return an empty `card_tags` list. Do not choose a merely related card.

Later match passes, when configured, contain only facts that received zero cards on the preceding pass. Reconsider those supplied cards independently; do not infer facts or cards that are absent from the current pass.

Do not rewrite or reinterpret the fact to fit a card.

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
