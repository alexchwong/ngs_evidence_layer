---
id: core.evidence.domain-current
semantic_type: evidence.domain_view
format: service
provides: [domain, cards, permitted_tags, text]
requires: []
runtime_invariants: [final_cmc_scoped_retrieval]
---
# Current domain evidence view

Evidence view for the current PTBG domain iteration. It exposes retrieved cards, exact permitted runtime card tags, and rendered evidence text.
