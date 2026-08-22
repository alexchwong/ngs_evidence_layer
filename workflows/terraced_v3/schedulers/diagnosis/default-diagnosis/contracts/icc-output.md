---
id: diagnosis.default.icc-output
semantic_type: diagnosis.icc.state
format: yaml
provides: ["diagnoses[].diagnosis_id", "diagnoses[].status", "diagnoses[].diagnosis", "diagnoses[].fact", "diagnoses[].reason", "diagnoses[].candidate_card_tags"]
requires: []
validator: icc
runtime_invariants: [sequential_icc_ids, supplied_candidate_card_tags, blind_to_who5]
---
# Independent ICC diagnosis output

Return YAML only:

```yaml
diagnoses:
  - diagnosis_id: "<sequential ICC diagnosis ID>"
    status: "<established or indeterminate>"
    diagnosis: "<ICC diagnostic label>"
    fact: "<concise patient-level ICC diagnostic statement>"
    reason: "<short auditable clinical justification>"
    candidate_card_tags: []
```

Angle-bracketed text describes required content only. It is not case information and must never be copied as a clinical conclusion.

Allowed `status`: `established`, `indeterminate`. Assign `ICC1`, `ICC2`, ... sequentially. `fact` is a concise reportable proposition ending with a full stop. Candidate card tags are hints only and must refer to cards supplied to this task.
