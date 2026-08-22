---
id: diagnosis.default.who5-output
semantic_type: diagnosis.who5.state
format: yaml
provides: ["diagnoses[].diagnosis_id", "diagnoses[].schema_disease", "diagnoses[].status", "diagnoses[].diagnosis", "diagnoses[].fact", "diagnoses[].reason", "diagnoses[].candidate_card_tags", "supporting_facts[].diagnosis_ids", "supporting_facts[].fact", "supporting_facts[].reason", "supporting_facts[].candidate_card_tags", "contradicting_facts[].diagnosis_ids", "contradicting_facts[].fact", "contradicting_facts[].reason", "contradicting_facts[].candidate_card_tags"]
requires: []
validator: who5
runtime_invariants: [allowed_schema_disease, sequential_who5_ids, supplied_candidate_card_tags, cmc_derived_only_by_core]
---
# WHO5 diagnosis output

Return YAML only with exactly these top-level keys:

```yaml
diagnoses:
  - diagnosis_id: DX1
    schema_disease: AML
    status: established
    diagnosis: "AML with NPM1 mutation"
    fact: "According to WHO5, the diagnosis is AML with NPM1 mutation."
    reason: "Short auditable clinical justification."
    candidate_card_tags: ["[card:0123456789ab]"]
supporting_facts:
  - diagnosis_ids: [DX1]
    fact: "A patient-level finding supports this diagnosis."
    reason: "Why the finding supports the diagnosis."
    candidate_card_tags: []
contradicting_facts:
  - diagnosis_ids: [DX1]
    fact: "A patient-level finding argues against or limits this diagnosis."
    reason: "Why the finding is contradictory or limiting."
    candidate_card_tags: []
```

Use only supplied canonical `schema_disease` values. Return concurrent WHO5 pathologies separately. Allowed `status`: `established`, `indeterminate`. Do not write CMC values; core derives CMC from validated WHO5 `schema_disease` values.
