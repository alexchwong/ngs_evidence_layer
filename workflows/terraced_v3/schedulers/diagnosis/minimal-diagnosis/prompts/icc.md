# Independent ICC diagnosis

Apply ICC classification independently to the supplied case and evidence. This branch is intentionally blind to WHO5 reasoning and must not infer or discuss a WHO5 answer.

{{output_contract}}

Additional task rules:
- return each concurrent ICC diagnosis that is established or materially plausible;
- `case_refs` are exact C#/V# patient-source IDs from the structured case that the proposition relies on;
- `card_refs` pair each literature-dependent fact to the supplied local `CARD nn` evidence blocks; pure patient observations should normally use `card_refs: []`; do not write runtime or source card IDs;
- keep each returned `fact` to one atomic reportable proposition wherever practical;
- do not mention CMC, WHO5, prior model output, or downstream domains.

# Structured immutable case
```json
{{case}}
```

# NGS assay scope
{{panel_scope}}

# Independent diagnostic evidence
{{evidence}}
