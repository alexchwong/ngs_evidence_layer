---
id: summarization.common.summary-plan
semantic_type: report.summary.plan
format: yaml
provides: ["dispositions[].statement_id", "dispositions[].decision", "dispositions[].reason", "sentences[].sentence_id", "sentences[].domain", "sentences[].source_statement_ids", "sentences[].draft_sentence"]
requires: []
validator: summary_plan
runtime_invariants: [every_statement_dispositioned, included_statements_covered, omitted_statements_absent, same_domain_composition]
---
# Summarization plan

Return YAML only:

```yaml
dispositions:
  - statement_id: S0001
    decision: include
    reason: null
  - statement_id: S0002
    decision: omit
    reason: "Redundant with the integrated diagnosis statement."
sentences:
  - sentence_id: diagnosis-1
    domain: diagnosis
    source_statement_ids: [S0001]
    draft_sentence: "A complete self-contained sentence."
```

Requirements:
- return one disposition for every supplied statement, in supplied order;
- use only `include` or `omit`;
- `include` requires `reason: null`; `omit` requires a concise audit reason;
- every included statement must occur in one or more sentence plans;
- omitted statements must occur in none;
- sentence array order is final report sentence order;
- several `source_statement_ids` in one sentence means merge;
- the same `statement_id` in several sentences means split;
- merge/split only within one domain;
- `draft_sentence` must preserve every proposition represented by its source statements.
