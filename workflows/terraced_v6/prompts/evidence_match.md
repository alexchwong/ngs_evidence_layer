# Batched reason-to-card evidence match

For EVERY supplied evidence item, decide which candidate cards are genuine elements of the clinical `reason`.

A card is an element of a reason only when the clinical proposition expressed by the card is actually present in that reason. Topical relevance, a shared gene/disease, or absence of contradiction is insufficient.

Select ALL candidate cards that independently match an element of the reason. More than one card may be selected for one reason. Do not require one card to support the whole reason: different cards may support different elements.

On a retry, an item may include `prior_failed_matches`. Treat every listed card tag as rejected. Read ALL prior audit feedback and use it to avoid repeating the same semantic mismatch. Rejected cards are removed from `candidate_card_tags`.

If none of the remaining candidate cards is an element of the reason, return an empty `card_tags` list. Do not choose a merely related card.

Do not rewrite or reinterpret the reason to fit a card. Previous auditor feedback is useful but non-authoritative.

Return YAML only, preserving evidence IDs and order:
```yaml
matches:
  - evidence_id: E0001
    card_tags:
      - "exact supplied [card:0123456789ab] tag"
      - "exact supplied [card:abcdef012345] tag"
  - evidence_id: E0002
    card_tags: []
```
