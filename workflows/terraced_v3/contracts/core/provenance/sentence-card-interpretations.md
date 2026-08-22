---
id: core.provenance.sentence-card-interpretations
semantic_type: provenance.sentence_card_interpretations
format: yaml
provides: ["sentences[].sentence_id", "sentences[].domain", "sentences[].sentence", "sentences[].source_fact_ids", "sentences[].cards[].card_tag", "sentences[].cards[].interpretation"]
requires: []
validator: deterministic
runtime_invariants: [deterministic_from_summary_card_tags]
---
# Sentence-to-card provenance

Core derives this artifact deterministically from the canonical summary and card corpus. It contains no model-generated evidence alignment.

```yaml
sentences:
  - sentence_id: treatment-1
    domain: treatment
    sentence: "A report sentence."
    source_fact_ids: [F0007]
    cards:
      - card_tag: "[card:0123456789ab]"
        interpretation: "The exact card interpretation."
```

`source_fact_ids` are the immutable cited facts used to construct the sentence. `cards` is the deterministic ordered expansion of the sentence's inherited `card_tags`.
