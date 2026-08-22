---
id: diagnosis.default.routing-output
semantic_type: diagnosis.routing.state
format: json
provides: ["schema_version", "final_cmcs[]", "diagnostic_cmc_history[]", "passes[]"]
requires: []
runtime_invariants: [final_cmcs_equal_who5_derived_cmcs, historical_cmcs_visible_during_diagnosis]
---
# Diagnosis routing output

Core-generated routing audit for the diagnosis scheduler. The scheduler controls the WHO5 reasoning topology; Python derives CMC values and records every CMC evidence environment encountered.
