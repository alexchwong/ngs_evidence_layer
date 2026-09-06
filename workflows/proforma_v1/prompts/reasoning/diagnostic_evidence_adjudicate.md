# Diagnostic evidence adjudication

## Output serialization contract
Return exactly one YAML mapping conforming to the declared schema. Return YAML only: no Markdown headings, no tables, no prose outside the mapping, no code fence around the answer, and no `---` document separators. The example below shows serialization/shape only; replace placeholders with your actual answer.

```yaml
adjudications:
  - rule_id: <exact supplied rule_id>
    card_tag: "[card:000000000000]"
    supports_rule: true
    reason: <reason>
```

Independently adjudicate only the supplied disputed rule/card pairs. Determine whether each card supports the exact rule. Do not assess patient applicability or final diagnosis. Return one adjudication for every dispute.

## Deterministic feedback from a prior structurally invalid adjudication
{{ input.audit_feedback }}

## Disputes
{{ input.disputes }}
