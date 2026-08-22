---
id: core.diagnosis.context
semantic_type: diagnosis.context
format: yaml
provides: [diagnoses, final_cmcs]
requires: []
runtime_invariants: [who5_cmc_consistency]
---
# Downstream diagnosis context

Convenience runtime object combining active WHO5 diagnoses and final WHO5-derived CMCs.

```yaml
diagnoses: []
final_cmcs: []
```
