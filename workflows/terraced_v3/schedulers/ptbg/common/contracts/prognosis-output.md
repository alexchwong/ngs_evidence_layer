---
id: ptbg.common.prognosis-output
semantic_type: ptbg.prognosis.state
format: yaml
provides: ["decisions[].variant_id", "decisions[].diagnosis_id", "decisions[].effect", "decisions[].scoring_system", "decisions[].surface", "decisions[].fact", "decisions[].reason", "decisions[].candidate_card_tags"]
requires: []
validator: domain
runtime_invariants: [exact_variant_x_diagnosis_scope, supplied_candidate_card_tags]
---
# Prognosis output

For every required detected variant × settled WHO5 diagnosis pair, return exactly:

```yaml
decisions:
  - variant_id: V1
    diagnosis_id: DX1
    effect: favorable
    scoring_system: "ELN 2022"
    surface: true
    fact: "A concise reportable prognostic fact."
    reason: "Short auditable justification."
    candidate_card_tags: []
```

Allowed `effect`: `favorable`, `adverse`, `neither`. `scoring_system` is a non-empty named system when applicable, otherwise null.
