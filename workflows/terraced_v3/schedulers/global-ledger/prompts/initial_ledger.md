# Terraced-v3 global hard-fact ledger

Fill all four downstream clinical domains in one coherent pass. Keep every decision explicitly disease-scoped. Do not write final report prose beyond surfaced fact fields. Candidate card tags must come from the matching evidence domain.

Return YAML only with exactly four top-level keys: prognosis, treatment, biomarker, germline. Each value must be the complete standard terraced-v3 domain artifact.

{{all_contracts}}

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
