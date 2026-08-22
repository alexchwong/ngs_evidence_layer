# Terraced-v3 variant-centric task

Consider this one detected variant across the downstream clinical questions. Keep every decision disease-scoped. Return hard decisions plus reportable fact/reason only where surfaced. `case_refs` are exact C#/V# patient-source IDs used by surfaced propositions. `card_tags` are final claimed literature evidence provenance and must use only exact tags from the matching domain evidence section that directly support the complete surfaced fact. Keep each surfaced fact atomic enough to be independently included or omitted later. Pure patient observations should normally use `card_tags: []`; literature-dependent interpretations require supporting cards. If an existing surfaced fact remains correct, preserve its fact text, case refs, and card tags exactly.

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
