# Batched semantic evidence-card match

For EVERY supplied evidence item, select the SINGLE candidate card that most directly and affirmatively supports the clinical `statement`. Use `reason` only to understand why the statement is being made and what aspect requires support.

Priorities:
1. same clinical claim/function, gene/variant, disease and context;
2. affirmative support for the statement rather than mere absence of contradiction;
3. when several cards are suitable, prefer wording closest to the statement/reason.

On a retry, an item may include `prior_failed_matches`. Treat every listed card as rejected. Read ALL prior audit feedback, not only the latest failure, and use it to avoid repeating the same semantic mismatch. Rejected cards are also removed from `candidate_card_ids`.

If none of the remaining candidate cards directly supports the proposition, declare no citation support instead of choosing a merely related card:

```yaml
card_id: null
source: null
quote: null
```

`source` is a concise human-readable authority/framework/study inferred from the selected card. `quote` should reproduce the most relevant wording faithfully enough to preserve polarity and meaning.

Do not rewrite the statement or reason to fit a card. Previous auditor feedback is useful but non-authoritative.

Return YAML only, preserving evidence IDs and order:
```yaml
matches:
  - evidence_id: E0001
    card_id: "exact supplied card_id or null"
    source: "human-readable source or null"
    quote: "closest relevant wording or null"
```
