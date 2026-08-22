---
id: core.statements.card-pairing
semantic_type: statements.card-pairing
format: yaml
provides: ["pairings[].candidate_id", "pairings[].card_refs"]
requires: []
validator: statement_card_pairing
runtime_invariants: [one_pairing_per_candidate, supplied_local_card_refs]
---
# Statement-to-card pairing

Return YAML only:

```yaml
pairings:
  - candidate_id: C1
    card_refs: ["CARD 01"]
```

Return exactly one row for every supplied candidate ID, in order. `card_refs` may be empty. Use only supplied local `CARD nn` labels; never emit runtime card IDs.
