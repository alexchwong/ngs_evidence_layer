---
id: summarization.minimal.summary-output
semantic_type: report.summary.sentences
format: yaml
provides: ["sentences[].sentence_id", "sentences[].domain", "sentences[].sentence", "sentences[].fact_ids", "sentences[].card_tags"]
requires: []
validator: summary_pairs
runtime_invariants: [all_cited_facts_covered, same_domain_fact_matching, card_tags_inherited_from_facts]
---
# Minimal canonical summarization output

Return YAML only:

```yaml
sentences:
  - sentence_id: prognosis-1
    domain: prognosis
    sentence: "A concise clinical sentence."
    fact_ids: [prognosis-V1-DX1]
    card_tags: ["[card:0123456789ab]"]
```

Use only supplied fact IDs. `card_tags` must be inherited from those facts exactly.
