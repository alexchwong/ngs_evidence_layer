# PTBG evidence adjudication

## Output serialization contract
Return exactly one YAML mapping conforming to the declared schema. Return YAML only: no Markdown headings, no tables, no prose outside the mapping, no code fence around the answer, and no `---` document separators. The example below shows serialization/shape only; replace placeholders with your actual answer.

```yaml
adjudications:
  - rule_id: <exact supplied rule_id>
    card_tag: "[card:000000000000]"
    supports_rule: true
    reason: <reason>
```

Adjudicate only the supplied evidence disputes. For every disputed rule/card pair decide whether the card supports the exact literature rule. Do not assess patient applicability or rewrite the clinical proposition.

This is an independent adjudication pass; do not simply repeat the prior evidence audit.

## Deterministic feedback from a prior invalid adjudication artifact
{{ input.audit_feedback }}

## Disputes
{{ input.disputes }}
