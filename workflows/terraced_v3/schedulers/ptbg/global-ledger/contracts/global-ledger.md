---
id: ptbg.global-ledger.global-ledger
semantic_type: ptbg.global.ledger
format: yaml
provides: [prognosis, treatment, biomarker, germline]
requires: []
validator: global_ledger
runtime_invariants: [all_four_domain_contracts_valid]
---
# Global PTBG ledger output

Return one mapping with exactly `prognosis`, `treatment`, `biomarker`, and `germline`, each conforming to the domain contract supplied in the prompt.
