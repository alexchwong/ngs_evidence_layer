## Prognosis contract
For every detected variant × settled WHO5 diagnosis pair, decide its molecular prognostic classification in the most applicable named prognostic scoring/classification system.

Return exactly:
```yaml
decisions:
  - variant_id: V1
    diagnosis_id: DX1
    effect: favorable
    scoring_system: "ELN 2022"
    surface: true
    fact: "... ."
    reason: "..."
    candidate_card_tags: []
```
Allowed effect values: `favorable`, `adverse`, `neither`. `scoring_system` is a non-empty string when a relevant named system applies, otherwise null. A `neither` result is usually `surface: false` unless clinically important.
