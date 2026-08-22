---
id: core.ptbg.task-scope
semantic_type: ptbg.task_scope
format: yaml
provides: ['required_pairs[]']
requires: []
runtime_invariants: [case_specific_domain_scope]
---
# Current PTBG task scope

Case-specific required decision rows for the current domain iteration. Core derives these from detected variants/genes and settled WHO5 diagnoses.

```yaml
required_pairs:
  - [V1, DX1]
```
