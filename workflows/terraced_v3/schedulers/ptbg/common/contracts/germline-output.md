---
id: ptbg.common.germline-output
semantic_type: ptbg.germline.state
format: yaml
provides: ["variant_decisions[].variant_id", "variant_decisions[].potentially_germline", "variant_decisions[].surface", "variant_decisions[].fact", "variant_decisions[].reason", "variant_decisions[].candidate_card_tags", "clinical_picture.supportive", "clinical_picture.surface", "clinical_picture.fact", "clinical_picture.reason", "clinical_picture.candidate_card_tags"]
requires: []
validator: domain
runtime_invariants: [exact_variant_scope, well_documented_germline_gene_rule, supplied_candidate_card_tags]
---
# Germline output

Return one variant decision for every required detected variant plus one case-level clinical-picture decision:

```yaml
variant_decisions:
  - variant_id: V1
    potentially_germline: false
    surface: false
    fact: null
    reason: null
    candidate_card_tags: []
clinical_picture:
  supportive: uncertain
  surface: true
  fact: "A concise clinical-picture statement when reportable."
  reason: "Short auditable justification."
  candidate_card_tags: []
```

`clinical_picture.supportive` must be `true`, `false`, or `uncertain`.
