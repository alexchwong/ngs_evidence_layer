---
id: ptbg.variant-centric.germline-clinical-picture
semantic_type: ptbg.germline.clinical_picture
format: yaml
provides: [clinical_picture.supportive, clinical_picture.surface, clinical_picture.fact, clinical_picture.reason, clinical_picture.candidate_card_tags]
requires: []
validator: germline_clinical_picture
runtime_invariants: []
---
# Germline clinical-picture output

```yaml
clinical_picture:
  supportive: "<true, false, or uncertain>"
  surface: "<true or false>"
  fact: "<concise reportable case-level germline clinical-picture statement, or null>"
  reason: "<short auditable justification, or null>"
  candidate_card_tags: []
```

Angle-bracketed text describes the required content only. It is not case information and must never be copied as a clinical conclusion.
