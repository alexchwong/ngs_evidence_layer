# Independent ICC diagnosis

Apply ICC classification independently to the supplied case and evidence. This branch is intentionally blind to WHO5 reasoning and must not infer or discuss a WHO5 answer.

{{output_contract}}

Additional task rules:
- return each concurrent ICC diagnosis that is established or materially plausible;
- candidate card tags are hints only; an empty list is appropriate for a case-derived conclusion without card support;
- do not mention CMC, WHO5, prior model output, or downstream domains.

# Structured immutable case
```json
{{case}}
```

# NGS assay scope
{{panel_scope}}

# Independent diagnostic evidence
{{evidence}}
