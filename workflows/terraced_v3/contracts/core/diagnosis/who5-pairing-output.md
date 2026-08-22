---
id: core.diagnosis.who5-pairing-output
semantic_type: diagnosis.who5.pairing-state
format: yaml
provides: ["diagnoses[].diagnosis_id", "diagnoses[].schema_disease", "diagnoses[].status", "diagnoses[].diagnosis", "diagnoses[].fact", "diagnoses[].reason", "diagnoses[].case_refs", "diagnoses[].card_refs", "supporting_facts[].diagnosis_ids", "supporting_facts[].fact", "supporting_facts[].reason", "supporting_facts[].case_refs", "supporting_facts[].card_refs", "contradicting_facts[].diagnosis_ids", "contradicting_facts[].fact", "contradicting_facts[].reason", "contradicting_facts[].case_refs", "contradicting_facts[].card_refs"]
requires: []
validator: who5_pairing
runtime_invariants: [allowed_schema_disease, sequential_who5_ids, supplied_case_refs, supplied_local_card_refs, cmc_derived_only_by_core]
---
# WHO5 diagnosis pairing output

Return YAML only with exactly these top-level keys:

```yaml
diagnoses:
  - diagnosis_id: "<sequential WHO5 diagnosis ID>"
    schema_disease: "<supplied canonical schema_disease value>"
    status: "<established or indeterminate>"
    diagnosis: "<WHO5 diagnostic label>"
    fact: "<concise patient-level WHO5 diagnostic statement>"
    reason: "<short auditable clinical justification>"
    case_refs: []
    card_refs: []
supporting_facts:
  - diagnosis_ids: ["<WHO5 diagnosis ID>"]
    fact: "<patient-level finding supporting the linked diagnosis>"
    reason: "<why this finding supports the linked diagnosis>"
    case_refs: []
    card_refs: []
contradicting_facts:
  - diagnosis_ids: ["<WHO5 diagnosis ID>"]
    fact: "<patient-level finding contradicting or limiting the linked diagnosis>"
    reason: "<why this finding contradicts or limits the linked diagnosis>"
    case_refs: []
    card_refs: []
```

Use only supplied canonical `schema_disease` values. Assign `DX1`, `DX2`, ... sequentially. Do not write CMC values.
Use only local `CARD nn` labels supplied in the evidence bundle. Do not write runtime card IDs or source card IDs.
Pure patient observations should normally use `card_refs: []`; literature-dependent interpretations should be paired only with cards that reasonably support them.
