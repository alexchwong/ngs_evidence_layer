---
id: ptbg.common.germline-output
semantic_type: ptbg.germline.state
format: yaml
provides: ["variant_decisions[].variant_id", "variant_decisions[].potentially_germline", "variant_decisions[].surface", "variant_decisions[].statement", "variant_decisions[].reason", "variant_decisions[].case_refs", "variant_decisions[].card_tags", "clinical_picture.supportive", "clinical_picture.surface", "clinical_picture.statement", "clinical_picture.reason", "clinical_picture.case_refs", "clinical_picture.card_tags"]
requires: []
validator: domain
runtime_invariants: [exact_variant_scope, well_documented_germline_gene_rule, supplied_case_refs, supplied_card_tags]
---
# Germline output

Return one variant decision for every required detected variant plus one case-level clinical-picture decision:

```yaml
variant_decisions:
  - variant_id: "<supplied variant ID>"
    potentially_germline: "<true or false>"
    surface: "<true or false>"
    statement: "<concise reportable germline statement, or null>"
    reason: "<short auditable justification, or null>"
    case_refs: []
    card_tags: []
clinical_picture:
  supportive: "<true, false, or uncertain>"
  surface: "<true or false>"
  statement: "<concise reportable clinical-picture statement, or null>"
  reason: "<short auditable justification, or null>"
  case_refs: []
  card_tags: []
```

Angle-bracketed text describes the required content only. It is not case information and must never be copied as a clinical conclusion.

`clinical_picture.supportive` must be `true`, `false`, or `uncertain`.

`case_refs` fields contain exact supplied C#/V# patient-source IDs used by surfaced statements. `card_tags` fields are populated by the downstream evidence-resolution step; clinical reasoning passes return them empty.
