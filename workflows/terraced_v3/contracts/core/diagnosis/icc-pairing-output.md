---
id: core.diagnosis.icc-pairing-output
semantic_type: diagnosis.icc.pairing-state
format: yaml
provides: ["diagnoses[].diagnosis_id", "diagnoses[].status", "diagnoses[].diagnosis", "diagnoses[].fact", "diagnoses[].reason", "diagnoses[].case_refs", "diagnoses[].card_refs"]
requires: []
validator: icc_pairing
runtime_invariants: [sequential_icc_ids, supplied_case_refs, supplied_local_card_refs, blind_to_who5]
---
# Independent ICC diagnosis pairing output

Return YAML only:

```yaml
diagnoses:
  - diagnosis_id: "<sequential ICC diagnosis ID>"
    status: "<established or indeterminate>"
    diagnosis: "<ICC diagnostic label>"
    fact: "<concise patient-level ICC diagnostic statement>"
    reason: "<short auditable clinical justification>"
    case_refs: []
    card_refs: []
```

Use only local `CARD nn` labels supplied in the evidence bundle. Do not write runtime card IDs or source card IDs.
Pure patient observations should normally use `card_refs: []`; literature-dependent interpretations should be paired only with cards that reasonably support them.
