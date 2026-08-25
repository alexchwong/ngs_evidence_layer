---
id: ptbg.evidence-first.normalized-evidence
semantic_type: evidence.normalized.domain
format: yaml
provides: ["evidence_items[].card_tag", "evidence_items[].diagnosis_ids", "evidence_items[].normalized_claim"]
requires: []
validator: normalized_evidence
runtime_invariants: [supplied_card_membership]
---
# Normalized evidence output

```yaml
evidence_items:
  - card_tag: "[card:0123456789ab]"
    diagnosis_ids: [DX1]
    normalized_claim: "Concise claim preserving the card's clinically material qualifiers."
```
