---
id: core.facts.reasonable-support-check
semantic_type: facts.reasonable-support-check
format: yaml
provides: ["assessments[].candidate_id", "assessments[].assessment", "assessments[].reason"]
requires: []
validator: reasonable_support_check
runtime_invariants: [one_assessment_per_candidate]
---
# Reasonable support check

Return YAML only:

```yaml
assessments:
  - candidate_id: C1
    assessment: supported
    reason: "<brief reason>"
```

Allowed `assessment`: `supported`, `partial`, `unsupported`.
Return exactly one row for every supplied candidate ID and do not add other top-level fields.
