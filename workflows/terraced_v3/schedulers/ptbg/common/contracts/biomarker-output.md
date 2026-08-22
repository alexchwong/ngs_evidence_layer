---
id: ptbg.common.biomarker-output
semantic_type: ptbg.biomarker.state
format: yaml
provides: ["decisions[].variant_id", "decisions[].diagnosis_id", "decisions[].mrd_usable", "decisions[].surface", "decisions[].statement", "decisions[].reason", "decisions[].case_refs", "decisions[].card_tags"]
requires: []
validator: domain
runtime_invariants: [exact_variant_x_diagnosis_scope, supplied_case_refs, supplied_card_tags]
---
# Biomarker/MRD output

For every required detected variant × settled WHO5 diagnosis pair, return exactly:

```yaml
decisions:
  - variant_id: "<supplied variant ID>"
    diagnosis_id: "<supplied diagnosis ID>"
    mrd_usable: "<true or false>"
    surface: "<true or false>"
    statement: "<concise molecular MRD statement, or null>"
    reason: "<short auditable justification>"
    case_refs: []
    card_tags: []
```

Angle-bracketed text describes the required content only. It is not case information and must never be copied as a clinical conclusion.

`case_refs` fields contain exact supplied C#/V# patient-source IDs used by surfaced statements. `card_tags` fields are populated by the downstream evidence-resolution step; clinical reasoning passes return them empty.
