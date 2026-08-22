## MRD/biomarker contract
For every detected variant × settled WHO5 diagnosis pair, decide whether that detected variant can be used as a molecular MRD biomarker in that disease context.

Return exactly:
```yaml
decisions:
  - variant_id: V1
    diagnosis_id: DX1
    mrd_usable: true
    surface: true
    fact: "... ."
    reason: "..."
    candidate_card_tags: []
```
Do not treat every persistent somatic mutation as an MRD marker. Surface clinically useful positive or cautionary statements.
