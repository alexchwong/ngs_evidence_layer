# Terraced-v3 adaptive targeted review

Review exactly one high-impact clinical decision cell. Do not reconsider unrelated cells. Compare the current validated cell against the immutable case, settled WHO5 disease context and the supplied domain evidence. Return `keep` when materially correct; otherwise return the complete corrected row. Candidate card tags must come from supplied evidence.

Return YAML only:
```yaml
action: keep
reason: "brief adjudication"
replacement: null
```
or use `action: replace` with the complete replacement row.

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
