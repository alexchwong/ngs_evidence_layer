---
id: core.diagnosis.bootstrap-evidence
semantic_type: evidence.diagnosis.bootstrap
format: service
provides: [cards, permitted_tags, text]
requires: []
runtime_invariants: [bootstrap_diagnosis_retrieval]
---
# Diagnosis bootstrap evidence

Runtime evidence view used before a WHO5-derived CMC has stabilised. It contains the diagnosis cards retrieved from the case genes and bootstrap CMC context, the exact permitted runtime card tags, and the rendered evidence text supplied to the model.
