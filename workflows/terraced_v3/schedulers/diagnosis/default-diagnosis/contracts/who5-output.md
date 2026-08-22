---
id: diagnosis.default.who5-output
semantic_type: diagnosis.who5.state
format: yaml
provides: ["diagnoses[].diagnosis_id", "diagnoses[].schema_disease", "diagnoses[].status", "diagnoses[].diagnosis", "diagnoses[].statement", "diagnoses[].reason", "diagnoses[].case_refs", "diagnoses[].card_tags"]
requires: []
validator: who5
runtime_invariants: [allowed_schema_disease, sequential_who5_ids, supplied_case_refs, supplied_card_tags, cmc_derived_only_by_core]
---
# WHO5 diagnosis output

Return YAML only with exactly these top-level keys:

```yaml
diagnoses:
  - diagnosis_id: "<sequential WHO5 diagnosis ID>"
    schema_disease: "<supplied canonical schema_disease value>"
    status: "<established or indeterminate>"
    diagnosis: "<WHO5 diagnostic label>"
    statement: "WHO5 classification: <same WHO5 diagnostic label>."
    reason: "<short auditable clinical justification using patient findings as premises>"
    case_refs: []
    card_tags: []
```

Angle-bracketed text describes required content only. It is not case information and must never be copied as a clinical conclusion.

Use only supplied canonical `schema_disease` values. Return concurrent WHO5 pathologies separately. Allowed `status`: `established`, `indeterminate`. Assign `DX1`, `DX2`, ... sequentially. Do not write CMC values; core derives CMC from validated WHO5 `schema_disease` values.

`case_refs` identify patient observations used in `reason`. Literature cards support the diagnostic `statement`; patient observations themselves are not separate reportable statements.
