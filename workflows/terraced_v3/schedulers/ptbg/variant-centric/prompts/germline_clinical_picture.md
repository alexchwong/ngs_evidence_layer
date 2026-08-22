# Terraced-v3 germline clinical-picture task

Decide only whether the supplied age, phenotype and family history support a germline predisposition syndrome. Do not use tumour-only VAF to prove or exclude constitutional origin. Use only the supplied case and germline evidence. Any surfaced fact must be an atomic, self-contained reportable proposition. `card_tags` are final provenance: use only supplied germline cards that directly support the complete proposition, or `card_tags: []` when the proposition is genuinely derived from the case alone. Preserve unchanged surfaced fact text and card tags verbatim on later passes.

{{output_contract}}

# Structured case
```json
{{case}}
```

# Germline evidence
{{evidence}}
