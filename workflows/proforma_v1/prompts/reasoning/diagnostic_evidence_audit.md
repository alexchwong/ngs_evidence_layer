# Diagnostic atomic evidence audit

## Output serialization contract
Return exactly one YAML mapping conforming to the declared schema. Return YAML only: no Markdown headings, no tables, no prose outside the mapping, no code fence around the answer, and no `---` document separators. The example below shows serialization/shape only; replace placeholders with your actual answer.

```yaml
audits:
  - rule_id: <exact supplied rule_id>
    card_tag: "[card:000000000000]"
    supports_rule: true
    comments: []
```

Audit every supplied rule/card pair. The only question is whether the card supports the exact literature/framework rule as written.

Do not decide whether this patient satisfies the rule. Do not decide the final diagnosis. Return one audit row for every supplied pair in one complete artifact, even when several pairs fail.

## Deterministic feedback from a prior invalid audit result
{{ input.audit_feedback }}

## Rule/card pairs
{{ input.audit_items }}
