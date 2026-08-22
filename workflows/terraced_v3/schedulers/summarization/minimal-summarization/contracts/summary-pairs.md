---
id: summarization.minimal.summary-pairs
semantic_type: report.summary.sentence_fact_pairs
format: yaml
provides: ["sentences[].sentence_id", "sentences[].domain", "sentences[].sentence", "sentences[].fact_ids"]
requires: []
validator: summary_pairs
runtime_invariants: [all_cited_facts_covered, same_domain_fact_matching]
---
# Minimal sentence/fact-pair output

Return YAML only:

```yaml
sentences:
  - sentence_id: diagnosis-1
    domain: diagnosis
    sentence: "A concise clinical sentence."
    fact_ids: [who5-DX1]
```

Every supplied surfaced fact ID must appear in at least one same-domain sentence. Do not emit card tags; core derives them from the paired cited facts.
