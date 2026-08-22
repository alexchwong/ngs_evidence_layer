---
id: core.diagnosis.who5.active
semantic_type: diagnosis.who5.active_list
format: yaml
provides:
  - '[].diagnosis_id'
  - '[].schema_disease'
  - '[].status'
  - '[].diagnosis'
requires: []
runtime_invariants: [active_who5_diagnoses_only]
---
# Active WHO5 diagnoses

Runtime list derived from the validated WHO5 diagnosis state. Only active/established diagnostic entities are exposed to downstream scheduler tasks.

```yaml
- diagnosis_id: DX1
  schema_disease: AML
  status: established
  diagnosis: AML with NPM1 mutation
```
