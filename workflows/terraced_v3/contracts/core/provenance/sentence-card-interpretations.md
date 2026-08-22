---
id: core.provenance.sentence-card-interpretations
semantic_type: report.sentence_card_interpretations
format: yaml
provides: ["sentences[].sentence_id", "sentences[].domain", "sentences[].sentence", "sentences[].fact_ids", "sentences[].cards[].card_tag", "sentences[].cards[].interpretation"]
requires: []
runtime_invariants: [deterministic_from_summary_card_tags]
---
# Sentence/card-interpretation provenance

Deterministically generated intermediate pairing every final report sentence with its matched fact IDs and the interpretations of the inherited card tags. No model creates or edits this mapping.

```yaml
sentences:
  - sentence_id: treatment-1
    domain: treatment
    sentence: "FLT3 is therapeutically actionable."
    fact_ids: [treatment-target-FLT3-DX1]
    cards:
      - card_tag: "[card:0123456789ab]"
        interpretation: "..."
```
