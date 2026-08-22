# Terraced-v3 variant-centric task

Consider this one detected variant across the downstream clinical questions. Keep every decision disease-scoped. Return hard decisions plus reportable statement/reason only where surfaced. `case_refs` are exact C#/V# patient-source IDs used by surfaced propositions. Citation pairing is separate downstream: return every card-tag field as an empty list. Keep each surfaced statement atomic enough to be independently included or omitted later. If an existing surfaced statement remains correct, preserve its statement text and case refs exactly.

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
