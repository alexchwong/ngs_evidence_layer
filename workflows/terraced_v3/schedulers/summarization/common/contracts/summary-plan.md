---
id: summarization.common.summary-plan
semantic_type: report.summary.plan
format: yaml
provides: ["dispositions[].fact_id", "dispositions[].decision", "dispositions[].reason", "sentences[].sentence_id", "sentences[].domain", "sentences[].source_fact_ids", "sentences[].draft_sentence"]
requires: []
validator: summary_plan
runtime_invariants: [every_fact_dispositioned, included_facts_covered, omitted_facts_absent, same_domain_composition]
---
# Summarization plan

Return YAML only:

```yaml
dispositions:
  - fact_id: F0001
    decision: include
    reason: null
  - fact_id: F0002
    decision: omit
    reason: "Redundant with the integrated diagnosis statement."
sentences:
  - sentence_id: diagnosis-1
    domain: diagnosis
    source_fact_ids: [F0001]
    draft_sentence: "A complete self-contained sentence."
```

Requirements:
- return one disposition for every supplied fact, in supplied order;
- use only `include` or `omit`;
- `include` requires `reason: null`; `omit` requires a concise audit reason;
- every included fact must occur in one or more sentence plans;
- omitted facts must occur in none;
- sentence array order is final report sentence order;
- several `source_fact_ids` in one sentence means merge;
- the same `fact_id` in several sentences means split;
- merge/split only within one domain;
- `draft_sentence` must preserve every proposition represented by its source facts.
