---
id: summarization.default.summary-output
semantic_type: report.summary.sentences
format: yaml
provides: ["sentences[].sentence_id", "sentences[].domain", "sentences[].sentence", "sentences[].fact_ids", "sentences[].card_tags"]
requires: []
validator: canonical_summary
runtime_invariants: [all_cited_facts_covered, same_domain_fact_matching, card_tags_inherited_from_facts]
---
# Canonical summarization output

The summarization scheduler must ultimately provide ordered sentence records:

```yaml
sentences:
  - sentence_id: prognosis-1
    domain: prognosis
    sentence: "A concise clinical sentence."
    fact_ids: [prognosis-V1-DX1]
    card_tags: ["[card:0123456789ab]"]
```

`card_tags` are not freely chosen by the summarizer: core requires them to equal the citations inherited from the paired locked facts.
