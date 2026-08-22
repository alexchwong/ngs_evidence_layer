# Terraced-v3 adaptive targeted review

Review exactly one high-impact clinical decision cell. Do not reconsider unrelated cells. Compare the current validated cell against the immutable case, settled WHO5 disease context and supplied domain evidence. `card_tags` are final claimed evidence provenance and must use only exact tags from supplied evidence that directly support the complete surfaced fact. Keep a surfaced fact atomic enough to be independently included or omitted later. Use `card_tags: []` only for a genuinely case-derived proposition needing no evidence card. If the current surfaced fact remains correct, preserve its fact text and card tags exactly; replace only when the proposition or provenance truly changes.

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
