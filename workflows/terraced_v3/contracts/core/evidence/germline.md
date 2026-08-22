---
id: core.evidence.germline
semantic_type: evidence.domain_view
format: service
provides: [domain, cards, permitted_tags, text]
requires: []
runtime_invariants: [germline_gene_scoped_retrieval]
---
# Germline evidence view

Runtime germline evidence view supplied to scheduler tasks that need case-level germline phenotype adjudication.
