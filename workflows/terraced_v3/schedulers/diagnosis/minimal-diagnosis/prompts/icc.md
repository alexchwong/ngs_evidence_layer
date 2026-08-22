# Independent ICC diagnosis

Apply ICC classification independently to the supplied case and evidence. This branch is intentionally blind to WHO5 reasoning and must not infer or discuss a WHO5 answer.

Return YAML only:

```yaml
diagnoses:
  - diagnosis_id: ICC1
    status: established
    diagnosis: "..."
    fact: "According to ICC, ... ."
    reason: "Short auditable clinical justification."
    candidate_card_tags: ["[card:0123456789ab]"]
```

Rules:
- return each concurrent ICC diagnosis that is established or materially plausible; use status `established` or `indeterminate`;
- assign sequential IDs ICC1, ICC2, ...;
- `fact` is a concise reportable proposition and must end with a full stop;
- `reason` explains why the fact follows from the supplied case/evidence; it is not hidden chain-of-thought;
- candidate card tags are hints only and must be exact supplied tags; use an empty list when the conclusion is case-derived without a supporting card;
- do not mention CMC, WHO5, prior model output, or downstream domains.

# Structured immutable case
```json
{{case}}
```

# NGS assay scope
{{panel_scope}}

# Independent diagnostic evidence
{{evidence}}
