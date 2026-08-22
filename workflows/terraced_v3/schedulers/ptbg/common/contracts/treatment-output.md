---
id: ptbg.common.treatment-output
semantic_type: ptbg.treatment.state
format: yaml
provides: ["decisions[].gene", "decisions[].diagnosis_id", "decisions[].drug_target", "decisions[].target_surface", "decisions[].target_fact", "decisions[].target_reason", "decisions[].target_candidate_card_tags", "decisions[].drug_resistance", "decisions[].resistance_surface", "decisions[].resistance_fact", "decisions[].resistance_reason", "decisions[].resistance_candidate_card_tags"]
requires: []
validator: domain
runtime_invariants: [exact_gene_x_diagnosis_scope, supplied_candidate_card_tags]
---
# Treatment output

For every required detected gene × settled WHO5 diagnosis pair, return exactly:

```yaml
decisions:
  - gene: "<supplied gene>"
    diagnosis_id: "<supplied diagnosis ID>"
    drug_target: "<true or false>"
    target_surface: "<true or false>"
    target_fact: "<concise alteration-qualified targetability fact, or null>"
    target_reason: "<short auditable justification, or null>"
    target_candidate_card_tags: []
    drug_resistance: "<true or false>"
    resistance_surface: "<true or false>"
    resistance_fact: "<concise alteration-qualified resistance fact, or null>"
    resistance_reason: "<short auditable justification, or null>"
    resistance_candidate_card_tags: []
```

Angle-bracketed text describes the required content only. It is not case information and must never be copied as a clinical conclusion.

Keep alteration-specific qualifiers; do not generalise beyond the detected alteration context.
