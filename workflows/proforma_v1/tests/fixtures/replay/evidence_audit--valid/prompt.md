# Fact-to-card evidence audit

The input is divided into independent JSON fact blocks named `<fact-1>...</fact-1>`, `<fact-2>...</fact-2>`, and so on.

Each block contains one clinical `fact` and ONLY the cards that the evidence matcher selected for that fact. Audit every supplied card independently against the fact in the SAME block. Do not infer, request, or audit any unmatched card.

For each supplied card answer one question:

- `card_is_element_of_reason`: is the clinical proposition expressed by this card actually an element of the fact?

A card about a different clinical use of the same gene is not an element of the fact. Topical relevance, a shared gene/disease, absence of contrary evidence, or merely compatible wording is insufficient.

A card does NOT need to support the whole fact. Different cards may support different elements of the same fact.

Use `risk: warning` only for non-gating fidelity/strength/context concerns when `card_is_element_of_reason` is still true. Use `comments: []` for an uncomplicated pass. For a failed card or a warning, give only a concise explanation of the mismatch or concern.

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
          - "The card addresses treatment response, not the prognostic element stated in the fact."
```
