# Terraced-v3 global clinical-statement ledger

Fill all four downstream clinical domains in one coherent pass. Keep every decision explicitly disease-scoped. Do not write final report prose beyond surfaced statement fields. `case_refs` are exact C#/V# patient-source IDs used by surfaced propositions. Citation pairing is a separate downstream step: return all card-tag fields as empty lists in this clinical reasoning pass. Keep each surfaced statement atomic enough to be independently included or omitted later. When a prior surfaced statement remains correct on a later pass, preserve its statement text and case refs exactly.

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
