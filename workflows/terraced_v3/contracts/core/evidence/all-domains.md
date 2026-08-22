---
id: core.evidence.all-domains
semantic_type: evidence.domain_view_map
format: service
provides: [prognosis, treatment, biomarker, germline]
requires: []
runtime_invariants: [final_cmc_scoped_retrieval]
---
# All PTBG domain evidence

Mapping from each PTBG domain to its runtime evidence view. Used by cross-domain schedulers such as global-ledger and variant-centric.
