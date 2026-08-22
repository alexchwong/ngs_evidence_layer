---
id: core.requirements.diagnosis.icc
semantic_type: diagnosis.icc.state
format: yaml
provides: []
requires: ["diagnoses[].diagnosis_id", "diagnoses[].diagnosis"]
runtime_invariants: []
---
# Input requirement: diagnosis.icc.state

Compatibility contract used during pipeline setup. An upstream module may use any output representation that declares this semantic type and provides the required fields.
