---
id: ptbg.variant-centric.variant-review
semantic_type: ptbg.variant.cross_domain_review
format: yaml
provides: [variant_id, prognosis, treatment, biomarker, germline_variant]
requires: []
validator: variant_cross_domain
runtime_invariants: [current_variant_only]
---
# Variant-centric cross-domain output

Return the current variant ID plus prognosis, treatment (when this variant owns the gene task), biomarker and germline-variant decisions using the corresponding PTBG field structures supplied in the prompt.
