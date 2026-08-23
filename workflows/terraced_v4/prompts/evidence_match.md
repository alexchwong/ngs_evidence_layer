# Semantic evidence-card match

Select the SINGLE supplied card that most directly supports the clinical reason.

Priorities:
1. correct gene/variant and disease/context;
2. clinical meaning that most directly supports the reason;
3. when several cards are semantically suitable, prefer the card whose wording is closest to the reason.

`source` is a concise human-readable authority/framework/study inferred from the selected card, e.g. `IPSS-M`, `ELN 2022`, `MIPSS70+ v2.0`, or `Smith et al.`.
`quote` should reproduce the most relevant wording from the selected card as faithfully as practical. Minor harmless transcription differences are not fatal; do not change polarity or meaning.

Do not rewrite the clinical reason to fit a card.

Return YAML only:
```yaml
card_id: "exact supplied card_id"
source: "human-readable source"
quote: "closest relevant wording"
```
