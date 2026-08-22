---
id: summarization.common.summary-output
semantic_type: report.summary.sentences
format: yaml
provides: ["dispositions[].fact_id", "dispositions[].decision", "dispositions[].reason", "sentences[].sentence_id", "sentences[].domain", "sentences[].sentence", "sentences[].source_fact_ids", "sentences[].card_tags"]
requires: []
validator: canonical_summary
runtime_invariants: [every_fact_dispositioned, included_facts_covered, omitted_facts_absent, same_domain_fact_matching, card_tags_inherited_from_source_facts]
---
# Canonical summary output

Core publishes this artifact deterministically from the validated summarization plan and individually paraphrased sentences:

```yaml
dispositions:
  - fact_id: F0001
    decision: include
    reason: null
sentences:
  - sentence_id: prognosis-1
    domain: prognosis
    sentence: "A self-contained final sentence."
    source_fact_ids: [F0001]
    card_tags: ["[card:0123456789ab]"]
```

The summarizer/paraphraser never chooses `card_tags`; core computes their ordered union from `source_fact_ids`.
