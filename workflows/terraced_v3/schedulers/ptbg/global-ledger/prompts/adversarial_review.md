# Terraced-v3 global-ledger adversarial review

Review the complete downstream clinical-statement ledger against the immutable case, settled WHO5 diagnoses and supplied evidence. Focus on clinically material errors, disease-scope transfer, overcalling, missed positive implications, and incorrect statement/reason wording. Do not rewrite domains that are already correct. Citation pairing is separate downstream: return all card-tag fields as empty lists. Within a corrected domain, preserve every still-correct surfaced `statement` and its `case_refs` exactly; change them only when the clinical proposition truly changes.

{{output_contract}}

# Initial validated ledger
```yaml
{{initial}}
```

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
