# Terraced-v3 germline clinical-picture task

Decide only whether the supplied age, phenotype and family history support a germline predisposition syndrome. Do not use tumour-only VAF to prove or exclude constitutional origin. Use only the supplied case and germline evidence. Any surfaced statement must be an atomic, self-contained reportable proposition. `case_refs` are exact C#/V# patient-source IDs used by surfaced propositions. Citation pairing is separate downstream: return `card_tags: []` in this clinical reasoning pass. Preserve unchanged surfaced statement text and case refs verbatim on later passes.

{{output_contract}}

# Structured case
```json
{{case}}
```

# Germline evidence
{{evidence}}
