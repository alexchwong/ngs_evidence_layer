---
id: core.facts.cited
semantic_type: clinical.facts.cited
format: yaml
provides:
  - facts[].fact_id
  - facts[].domain
  - facts[].fact
  - facts[].card_tags
requires: []
runtime_invariants: [immutable_fact_text_and_card_attribution, local_evidence_check_before_acceptance]
---
# Active immutable cited fact ledger

The minimal reportable-fact list handed upstream to summarization. Each `fact_id` is assigned deterministically by core when a proposition is first accepted. Its reportable `fact` text and `card_tags` are immutable together. Later reasoning may retain the exact fact or withdraw/replace it; replacements receive a new `fact_id`.

```yaml
facts:
  - fact_id: F0001
    domain: prognosis
    fact: "A complete self-contained reportable proposition."
    card_tags: ["[card:0123456789ab]"]
```

`card_tags: []` is reserved for genuinely case-derived propositions that do not depend on a literature card.
