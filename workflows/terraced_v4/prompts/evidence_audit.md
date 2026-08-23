# Batched citation-match risk audit

Audit EVERY supplied selected card/source/quote against its clinical reason.

This is NOT an entailment tribunal. Do not fail a card merely because wording is not logically exhaustive, because an association is not causation, or because you can imagine a more qualified sentence.

Set `obvious_mismatch: true` only for clear matching failures such as wrong gene, wrong disease/context, unrelated clinical topic, a quote plainly attributed to the wrong card, or a source label plainly inconsistent with the card.

A card supporting a different clinical use of the same gene does not support the current claim and is an obvious mismatch.

The auditor is advisory, not authoritative. For every `obvious_mismatch: true`, `comments` MUST explain the concrete mismatch precisely enough that the matcher can reconsider it. Use `risk: warning` for arguable fidelity/strength/wording concerns that a human should inspect; warnings do not reject the card.

Return YAML only, preserving evidence IDs and order:
```yaml
audits:
  - evidence_id: E0001
    obvious_mismatch: false
    risk: "none | warning"
    comments: []
```
