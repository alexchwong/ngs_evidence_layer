# Terraced-v3 variant-centric task

Consider this one detected variant across the four downstream clinical questions. Keep every decision disease-scoped. Return hard decisions plus reportable fact/reason only where surfaced. Candidate card tags must come from the matching domain evidence section.

Variant:
```yaml
{{variant}}
```
Treatment owner for this gene: `{{include_treatment}}`. If false, return `treatment: null`.

Return YAML only with exactly:
```yaml
variant_id: {{variant_id}}
prognosis:
  decisions: []
treatment: null
biomarker:
  decisions: []
germline_variant:
  variant_id: {{variant_id}}
  potentially_germline: false
  surface: false
  fact: null
  reason: null
  candidate_card_tags: []
```
The prognosis/biomarker decision rows use the standard terraced-v3 contracts for this variant × every settled diagnosis. When treatment owner is true, treatment contains the standard treatment decisions mapping for this gene × every settled diagnosis.

# Structured case
```json
{{case}}
```

# Settled WHO5 diagnoses
```yaml
{{diagnoses}}
```

# Evidence by domain
{{evidence}}
