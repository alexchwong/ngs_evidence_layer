## Treatment contract
For every detected gene × settled WHO5 diagnosis pair, decide separately whether the detected alteration context makes the gene a drug target and whether it is associated with drug resistance.

Return exactly:
```yaml
decisions:
  - gene: FLT3
    diagnosis_id: DX1
    drug_target: true
    target_surface: true
    target_fact: "... ."
    target_reason: "..."
    target_candidate_card_tags: []
    drug_resistance: false
    resistance_surface: false
    resistance_fact: null
    resistance_reason: null
    resistance_candidate_card_tags: []
```
Boolean decisions are hard facts. Surface positive or otherwise clinically important implications only. Keep alteration-specific qualifiers in the fact/reason; do not generalise a gene-wide statement beyond the detected alteration.
