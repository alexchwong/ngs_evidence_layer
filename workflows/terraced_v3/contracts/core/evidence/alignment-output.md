---
id: core.evidence.alignment-output
semantic_type: evidence.fact_card_alignment
format: yaml
provides: ["alignments[].fact_id", "alignments[].citation"]
requires: []
validator: validate_evidence_alignment_text
runtime_invariants: [supplied_card_membership, disease_scoped_card_permission]
---
# Fact/reason to card alignment output

Return YAML only:

```yaml
alignments:
  - fact_id: prognosis-V1-DX1
    citation: "[card:0123456789ab]"
```

`citation` may be null. If non-null, it must contain only exact supplied runtime card tags genuinely supporting the stated reason sufficiently to justify the fact.
