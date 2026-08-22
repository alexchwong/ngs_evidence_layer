---
id: diagnosis.minimal.who5-output
semantic_type: diagnosis.who5.state
format: yaml
provides: ["diagnoses[].diagnosis_id", "diagnoses[].schema_disease", "diagnoses[].status", "diagnoses[].diagnosis", "diagnoses[].fact", "diagnoses[].reason", "diagnoses[].candidate_card_tags", "supporting_facts[].diagnosis_ids", "supporting_facts[].fact", "supporting_facts[].reason", "supporting_facts[].candidate_card_tags", "contradicting_facts[].diagnosis_ids", "contradicting_facts[].fact", "contradicting_facts[].reason", "contradicting_facts[].candidate_card_tags"]
requires: []
validator: who5
runtime_invariants: [allowed_schema_disease, sequential_who5_ids, supplied_candidate_card_tags, cmc_derived_only_by_core]
---
# WHO5 diagnosis output

Return YAML only with exactly these top-level keys:

```yaml
diagnoses:
  - diagnosis_id: "<sequential WHO5 diagnosis ID>"
    schema_disease: "<supplied canonical schema_disease value>"
    status: "<established or indeterminate>"
    diagnosis: "<WHO5 diagnostic label>"
    fact: "<concise patient-level WHO5 diagnostic statement>"
    reason: "<short auditable clinical justification>"
    candidate_card_tags: []
supporting_facts:
  - diagnosis_ids: ["<WHO5 diagnosis ID>"]
    fact: "<patient-level finding supporting the linked diagnosis>"
    reason: "<why this finding supports the linked diagnosis>"
    candidate_card_tags: []
contradicting_facts:
  - diagnosis_ids: ["<WHO5 diagnosis ID>"]
    fact: "<patient-level finding contradicting or limiting the linked diagnosis>"
    reason: "<why this finding contradicts or limits the linked diagnosis>"
    candidate_card_tags: []
```

Angle-bracketed text describes required content only. It is not case information and must never be copied as a clinical conclusion.

Use only supplied canonical `schema_disease` values. Return concurrent WHO5 pathologies separately. Allowed `status`: `established`, `indeterminate`. Assign `DX1`, `DX2`, ... sequentially. Do not write CMC values; core derives CMC from validated WHO5 `schema_disease` values.
