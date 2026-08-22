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
  - variant_id: "<supplied variant ID>"
    diagnosis_id: "<supplied diagnosis ID>"
    effect: "<favorable, adverse, or neither>"
    scoring_system: "<applicable named scoring system, or null>"
    surface: "<true or false>"
    fact: "<concise reportable prognostic fact, or null>"
    reason: "<short auditable justification>"
    candidate_card_tags: []
```

Angle-bracketed text describes the required content only. It is not case information and must never be copied as a clinical conclusion.

Allowed `effect`: `favorable`, `adverse`, `neither`. `scoring_system` is a non-empty named system when applicable, otherwise null.
