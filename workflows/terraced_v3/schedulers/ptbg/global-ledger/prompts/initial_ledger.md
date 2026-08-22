# Terraced-v3 global hard-fact ledger

Fill all four downstream clinical domains in one coherent pass. Keep every decision explicitly disease-scoped. Do not write final report prose beyond surfaced fact fields. `case_refs` are exact C#/V# patient-source IDs used by surfaced propositions. `card_tags` are final claimed literature evidence provenance and must use only exact tags from the matching evidence domain that directly support the complete surfaced fact. Keep each surfaced fact atomic enough to be independently included or omitted later. Pure patient observations should normally use `card_tags: []`; literature-dependent interpretations require supporting cards. When a prior surfaced fact remains correct on a later pass, preserve its fact text, case refs, and card tags exactly.

# Global output envelope
{{output_contract}}

# Domain contracts
## Prognosis
{{prognosis_contract}}

## Treatment
{{treatment_contract}}

## Biomarker/MRD
{{biomarker_contract}}

## Germline
{{germline_contract}}

# Structured immutable case
```json
{{case}}
```

# Settled WHO5 diagnoses and final CMCs
```yaml
{{diagnoses}}
```

# Required scopes
```yaml
{{scopes}}
```

# Evidence by domain
{{evidence}}
