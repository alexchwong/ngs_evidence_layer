# Independent ICC diagnosis

Apply ICC classification independently to the supplied case and evidence. This branch is intentionally blind to WHO5 reasoning and must not infer or discuss a WHO5 answer.

{{output_contract}}

Additional task rules:
- return each concurrent ICC diagnosis that is established or materially plausible;
- `card_tags` are the final claimed evidence provenance for each diagnosis fact: use only exact supplied card tags that directly support the complete proposition; use `[]` only for a genuinely case-derived conclusion that does not depend on a literature card;
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
