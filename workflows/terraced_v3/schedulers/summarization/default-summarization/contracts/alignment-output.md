---
id: summarization.default.alignment-output
semantic_type: report.sentence_fact_alignment
format: yaml
provides: ["alignments[].sentence_id", "alignments[].fact_ids"]
requires: []
validator: sentence_alignment
runtime_invariants: [same_domain_fact_matching, no_unsupported_fact_attachment]
---
# Sentence-to-fact alignment output

Return YAML only:

```yaml
alignments:
  - sentence_id: diagnosis-1
    fact_ids: [who5-DX1]
```

Include every supplied sentence ID exactly once and preserve order. Use only supplied fact IDs from the same clinical domain. List every fact represented by the sentence without duplicates.
