---
id: core.facts.cited
semantic_type: clinical.facts.cited
format: yaml
provides:
  - facts[].fact_id
  - facts[].domain
  - facts[].fact
  - facts[].case_refs
  - facts[].card_tags
requires: []
runtime_invariants: [immutable_fact_text_and_provenance, local_evidence_check_before_acceptance]
---
# Active immutable cited fact ledger

The minimal reportable-fact list handed upstream to summarization. Each `fact_id` is assigned deterministically by core when a proposition is first accepted. Its reportable `fact` text, patient-source `case_refs`, and literature `card_tags` are immutable together. Later reasoning may retain the exact fact or withdraw/replace it; replacements receive a new `fact_id`.

```yaml
facts:
  - fact_id: F0001
    domain: prognosis
    fact: "A complete self-contained reportable proposition."
    case_refs: [V1]
    card_tags: ["[card:0123456789ab]"]
```

`case_refs` identify exact structured-case C#/V# sources used by the proposition. `card_tags` contain only literature provenance. Pure patient observations normally have `card_tags: []`, but they are still locally reviewed so a literature-dependent inference cannot evade checking by dropping its cards.
