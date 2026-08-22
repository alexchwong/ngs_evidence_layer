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
## Treatment contract
For every detected gene × settled WHO5 diagnosis pair, decide separately whether the detected alteration context makes the gene a drug target and whether it is associated with drug resistance.

Return exactly:
```yaml
decisions:
  - gene: FLT3
    diagnosis_id: DX1
    drug_target: true
    target_surface: true
    target_fact: "... ."
    target_reason: "..."
    target_candidate_card_tags: []
    drug_resistance: false
    resistance_surface: false
    resistance_fact: null
    resistance_reason: null
    resistance_candidate_card_tags: []
```
Boolean decisions are hard facts. Surface positive or otherwise clinically important implications only. Keep alteration-specific qualifiers in the fact/reason; do not generalise a gene-wide statement beyond the detected alteration.
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
## Germline contract
For every detected variant, decide whether its gene is a well-documented germline predisposition gene for haematological malignancy and therefore the finding is potentially germline. Separately decide whether the supplied clinical picture supports a germline syndrome.

Return exactly:
```yaml
variant_decisions:
  - variant_id: V1
    potentially_germline: false
    surface: false
    fact: null
    reason: null
    candidate_card_tags: []
clinical_picture:
  supportive: false
  surface: false
  fact: null
  reason: null
  candidate_card_tags: []
```
`supportive` must be `true`, `false`, or `uncertain`. Potential germline status must be based on well-documented germline predisposition genes, not VAF alone. The clinical-picture decision may use age, phenotype and family history supplied in the case.
