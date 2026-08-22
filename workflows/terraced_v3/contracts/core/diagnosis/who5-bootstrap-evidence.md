---
id: core.diagnosis.who5-bootstrap-evidence
semantic_type: evidence.diagnosis.bootstrap
format: service
provides: [cards, permitted_tags, text]
requires: []
runtime_invariants: [bootstrap_diagnosis_retrieval, who5_publication_filter]
---
# WHO5 bootstrap diagnosis evidence

Runtime diagnosis evidence view used by a one-pass WHO5 scheduler before a WHO5-derived CMC has stabilised. The draw is filtered by the WHO5 publication keys configured in `workflows/terraced_v3/corpus_filters.yaml`.
