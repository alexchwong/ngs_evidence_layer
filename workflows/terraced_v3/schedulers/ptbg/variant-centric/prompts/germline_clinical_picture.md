# Terraced-v3 germline clinical-picture task

Decide only whether the supplied age, phenotype and family history support a germline predisposition syndrome. Do not use tumour-only VAF to prove or exclude constitutional origin. Use only the supplied case and germline evidence.

Return YAML only:
```yaml
clinical_picture:
  supportive: false
  surface: false
  fact: null
  reason: null
  candidate_card_tags: []
```
`supportive` must be true, false, or uncertain.

# Structured case
```json
{{case}}
```

# Germline evidence
{{evidence}}
