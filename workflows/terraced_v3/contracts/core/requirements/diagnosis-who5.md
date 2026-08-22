---
id: core.requirements.diagnosis.who5
semantic_type: diagnosis.who5.state
format: yaml
provides: []
requires: ["diagnoses[].diagnosis_id", "diagnoses[].schema_disease"]
runtime_invariants: []
---
# Input requirement: diagnosis.who5.state

Compatibility contract used during pipeline setup. An upstream module may use any output representation that declares this semantic type and provides the required fields.
