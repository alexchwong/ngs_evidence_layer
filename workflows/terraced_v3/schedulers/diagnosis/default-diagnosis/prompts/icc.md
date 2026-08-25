# Independent ICC diagnosis

Apply ICC classification independently to the supplied case and evidence. This branch is intentionally blind to WHO5 reasoning and must not infer or discuss a WHO5 answer.

{{output_contract}}

Additional task rules:
- return each concurrent ICC diagnosis that is established or materially plausible;
- `case_refs` are exact C#/V# patient-source IDs from the structured case that the proposition relies on;
- `card_refs` pair each literature-dependent statement to the supplied local `CARD nn` evidence blocks; do not write runtime or source card IDs;
- `statement` must directly answer the ICC diagnosis question; patient findings belong in `reason`, not as separate statements;
- return `statement` exactly as `ICC classification: <diagnosis>.` using the same diagnostic label from the row;
- do not mention CMC, WHO5, prior model output, or downstream domains.

# Structured immutable case
```json
{{case}}
```

# NGS assay scope
{{panel_scope}}

# Independent diagnostic evidence
{{evidence}}
