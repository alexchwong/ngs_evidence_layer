---
id: diagnosis.minimal.icc-output
semantic_type: diagnosis.icc.state
format: yaml
provides: ["diagnoses[].diagnosis_id", "diagnoses[].status", "diagnoses[].diagnosis", "diagnoses[].fact", "diagnoses[].reason", "diagnoses[].case_refs", "diagnoses[].card_tags"]
requires: []
validator: icc
runtime_invariants: [sequential_icc_ids, supplied_case_refs, supplied_card_tags, blind_to_who5]
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
    case_refs: []
    card_tags: []
```

Angle-bracketed text describes required content only. It is not case information and must never be copied as a clinical conclusion.

Allowed `status`: `established`, `indeterminate`. Assign `ICC1`, `ICC2`, ... sequentially. `fact` is a concise reportable proposition ending with a full stop. `case_refs` contain exact C#/V# patient-source IDs used by the proposition. `card_tags` are final claimed literature provenance and must use only exact cards supplied to this task. Pure patient observations should normally use `card_tags: []`; literature-dependent interpretations require supporting cards.
