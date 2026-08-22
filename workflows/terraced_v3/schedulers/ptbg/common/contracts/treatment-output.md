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
  - gene: FLT3
    diagnosis_id: DX1
    drug_target: true
    target_surface: true
    target_fact: "A concise alteration-qualified targetability fact."
    target_reason: "Short auditable justification."
    target_candidate_card_tags: []
    drug_resistance: false
    resistance_surface: false
    resistance_fact: null
    resistance_reason: null
    resistance_candidate_card_tags: []
```

Keep alteration-specific qualifiers; do not generalise beyond the detected alteration context.
