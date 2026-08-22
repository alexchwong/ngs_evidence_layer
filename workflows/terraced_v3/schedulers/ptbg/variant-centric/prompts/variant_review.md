# Terraced-v3 variant-centric task

Consider this one detected variant across the downstream clinical questions. Keep every decision disease-scoped. Return hard decisions plus reportable fact/reason only where surfaced. Candidate card tags must come from the matching domain evidence section.

# Scheduler-specific output envelope
{{output_contract}}

# Standard domain field contracts
## Prognosis
{{prognosis_contract}}

## Treatment
{{treatment_contract}}

## Biomarker/MRD
{{biomarker_contract}}

## Germline
{{germline_contract}}

Variant:
```yaml
{{variant}}
```
Treatment owner for this gene: `{{include_treatment}}`. If false, return `treatment: null`.

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
