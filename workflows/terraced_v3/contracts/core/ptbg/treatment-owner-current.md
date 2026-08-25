---
id: core.ptbg.treatment-owner-current
semantic_type: ptbg.treatment_owner_flag
format: text
provides: [value]
requires: []
runtime_invariants: [one_treatment_owner_per_gene]
---
# Current variant treatment-owner flag

Boolean runtime flag used by variant-centric scheduling to avoid duplicating a gene-level treatment decision across multiple variants of the same gene.
