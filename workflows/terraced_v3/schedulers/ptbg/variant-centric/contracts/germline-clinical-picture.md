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
  supportive: uncertain
  surface: true
  fact: "A concise case-level germline clinical-picture statement."
  reason: "Short auditable justification."
  candidate_card_tags: []
```
