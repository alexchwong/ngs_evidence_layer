# Terraced-v3 adaptive targeted review

Review exactly one high-impact clinical decision cell. Do not reconsider unrelated cells. Compare the current validated cell against the immutable case, settled WHO5 disease context and supplied domain evidence. `case_refs` are exact C#/V# patient-source IDs used by surfaced propositions. Citation pairing is separate downstream: return all card-tag fields as empty lists. Keep a surfaced statement atomic enough to be independently included or omitted later. If the current surfaced statement remains correct, preserve its statement text and case refs exactly; replace only when the proposition truly changes.

{{output_contract}}

# Cell
```yaml
{{cell}}
```

# Structured case
```json
{{case}}
```

# Settled WHO5 diagnoses
```yaml
{{diagnoses}}
```

# Evidence
{{evidence}}
