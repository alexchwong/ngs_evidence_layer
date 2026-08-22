# Terraced-v3 global-ledger adversarial review

Review the complete validated downstream hard-fact ledger against the immutable case, settled WHO5 diagnoses and supplied evidence. Focus on clinically material errors, disease-scope transfer, overcalling, missed positive implications, and incorrect fact/reason wording. Do not rewrite domains that are already correct.

Return a PATCH only:
```yaml
changes:
  - domain: prognosis
    reason: "why the validated domain must change"
    replacement:
      decisions: []
```
Each replacement must be the COMPLETE standard artifact for that domain. Use `changes: []` when no material correction is warranted. Python will apply replacements deterministically.

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
