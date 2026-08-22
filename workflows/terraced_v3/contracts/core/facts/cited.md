---
id: core.facts.cited
semantic_type: clinical.facts.cited
format: yaml
provides:
  - facts[].fact_id
  - facts[].domain
  - facts[].subject
  - facts[].decision
  - facts[].fact
  - facts[].reason
  - facts[].citation
requires: []
runtime_invariants: [reason_to_card_semantic_alignment, disease_scoped_card_permission]
---
# Locked cited fact ledger

A frozen list of surfaced clinical facts and short auditable reasons after independent core evidence alignment. Schedulers consuming this ledger may re-express these facts but must not alter the clinical propositions or evidence provenance.
