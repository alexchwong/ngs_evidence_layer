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
