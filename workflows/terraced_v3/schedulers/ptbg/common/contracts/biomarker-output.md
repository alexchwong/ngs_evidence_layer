---
id: ptbg.common.biomarker-output
semantic_type: ptbg.biomarker.state
format: yaml
provides: ["decisions[].variant_id", "decisions[].diagnosis_id", "decisions[].mrd_usable", "decisions[].surface", "decisions[].fact", "decisions[].reason", "decisions[].candidate_card_tags"]
requires: []
validator: domain
runtime_invariants: [exact_variant_x_diagnosis_scope, supplied_candidate_card_tags]
---
# Biomarker/MRD output

For every required detected variant × settled WHO5 diagnosis pair, return exactly:

```yaml
decisions:
  - variant_id: V1
    diagnosis_id: DX1
    mrd_usable: true
    surface: true
    fact: "A concise molecular MRD fact."
    reason: "Short auditable justification."
    candidate_card_tags: []
```
