# Terraced-v3 germline clinical-picture task

Decide only whether the supplied age, phenotype and family history support a germline predisposition syndrome. Do not use tumour-only VAF to prove or exclude constitutional origin. Use only the supplied case and germline evidence. Any surfaced fact must be an atomic, self-contained reportable proposition. `case_refs` are exact C#/V# patient-source IDs used by surfaced propositions. `card_tags` are final literature provenance: use only supplied germline cards that directly support the complete proposition, Pure patient observations should normally use `card_tags: []`; literature-dependent interpretations require supporting cards. Preserve unchanged surfaced fact text, case refs and card tags verbatim on later passes.

{{output_contract}}

# Structured case
```json
{{case}}
```

# Germline evidence
{{evidence}}
