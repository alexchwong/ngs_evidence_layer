---
id: diagnosis.minimal.icc-output
semantic_type: diagnosis.icc.state
format: yaml
provides: ["diagnoses[].diagnosis_id", "diagnoses[].status", "diagnoses[].diagnosis", "diagnoses[].fact", "diagnoses[].reason", "diagnoses[].candidate_card_tags"]
requires: []
validator: icc
runtime_invariants: [sequential_icc_ids, supplied_candidate_card_tags, blind_to_who5]
---
# Independent ICC diagnosis output

Return YAML only:

```yaml
diagnoses:
  - diagnosis_id: ICC1
    status: established
    diagnosis: "AML with mutated NPM1"
    fact: "According to ICC, AML with mutated NPM1 is diagnosed."
    reason: "Short auditable clinical justification."
    candidate_card_tags: ["[card:0123456789ab]"]
```

Allowed `status`: `established`, `indeterminate`. Assign `ICC1`, `ICC2`, ... sequentially. `fact` is a concise reportable proposition ending with a full stop. Candidate card tags are hints only and must refer to cards supplied to this task.
