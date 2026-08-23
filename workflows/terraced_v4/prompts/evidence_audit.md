# Citation-match risk audit

Audit only the selected card/source/quote against the supplied reason.

This is NOT an entailment tribunal. Do not fail a card merely because wording is not logically exhaustive, because an association is not causation, or because you can imagine a more qualified sentence.

Set `obvious_mismatch: true` only for clear matching failures such as wrong gene, wrong disease/context, unrelated clinical topic, a quote plainly attributed to the wrong card, or a source label plainly inconsistent with the card.

The auditor is advisory, not authoritative. When you set `obvious_mismatch: true`, `comments` MUST explain the concrete mismatch precisely enough that the matcher can reconsider it. Do not merely say "unsupported", "weak", or "incorrect".

Use `risk: warning` for arguable fidelity/strength/wording concerns that a human should inspect. These warnings do not automatically reject the card.

Return YAML only:
```yaml
obvious_mismatch: false
risk: "none | warning"
comments: []
```
