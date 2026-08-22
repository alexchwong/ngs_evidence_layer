---
id: core.facts.evidence-check
semantic_type: clinical.fact_evidence_check
format: yaml
provides: ["checks[].candidate_id", "checks[].supported", "checks[].issue"]
requires: []
validator: fact_evidence_check
runtime_invariants: [reject_only, exact_candidate_order]
---
# Local fact evidence-check output

Return YAML only:

```yaml
checks:
  - candidate_id: C1
    supported: true
    issue: null
  - candidate_id: C2
    supported: false
    issue: "The claimed card does not support the treatment implication stated in the fact."
```

Copy every supplied `candidate_id` exactly once in supplied order. The checker never repairs a fact or its citations.
