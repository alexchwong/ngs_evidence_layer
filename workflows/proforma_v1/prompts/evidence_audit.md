# Reason-to-card evidence audit

Audit EVERY selected card independently against the clinical `reason`.

For each selected card answer one question:

- `card_is_element_of_reason`: is the clinical proposition expressed by this card actually an element of the reason?

A card about a different clinical use of the same gene is not an element of the reason. Topical relevance, a shared gene/disease, absence of contrary evidence, or merely compatible wording is insufficient.

A card does NOT need to support the whole reason. Different cards may support different elements of the same reason.

When a card fails, make `comments` operational for the next evidence-match attempt: state concisely WHY it is not an element of the reason (for example wrong clinical function, wrong disease, wrong gene/variant, wrong framework, wrong polarity, or only indirect/related evidence). Do not prescribe a replacement clinical answer or invent a card.

Use `risk: warning` for non-gating fidelity/strength/context concerns when `card_is_element_of_reason` is still true. Give concise comments explaining any failure or warning.

Return YAML only, preserving evidence IDs, card tags and order:
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
          - "The card addresses treatment response, not the prognostic element stated in the reason."
```
