---
id: core.facts.evidence-check
semantic_type: clinical.fact_evidence_check
format: yaml
provides: ["checks[].candidate_id", "checks[].supported", "checks[].issue_code", "checks[].issue"]
requires: []
validator: fact_evidence_check
runtime_invariants: [reject_only, exact_candidate_order, typed_failure_reason]
---
# Local fact provenance/support-check output

Return YAML only:

```yaml
checks:
  - candidate_id: C1
    supported: true
    issue_code: null
    issue: null
  - candidate_id: C2
    supported: false
    issue_code: "scope_mismatch"
    issue: "The claimed card concerns a different disease context from the interpretation stated in the fact."
```

Allowed `issue_code` values when `supported: false`:

- `observation_should_be_cardless`
- `missing_card_evidence`
- `irrelevant_card`
- `incomplete_rule_support`
- `authority_mismatch`
- `unsupported_inference`
- `scope_mismatch`

Copy every supplied `candidate_id` exactly once in supplied order. When `supported: true`, both `issue_code` and `issue` must be null. The checker never repairs a fact or its provenance.
