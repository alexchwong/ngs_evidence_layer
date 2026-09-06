# Diagnostic evidence rescue matching

## Output serialization contract
Return exactly one YAML mapping conforming to the declared schema. Return YAML only: no Markdown headings, no tables, no prose outside the mapping, no code fence around the answer, and no `---` document separators. The example below shows serialization/shape only; replace placeholders with your actual answer.

```yaml
assignments:
  - rule_id: <exact supplied rule_id>
    card_tags: []
```

The diagnostic owners already attempted evidence assignment. Match only the supplied rules that remain unassigned.

For every rescue rule, return exactly one row. Use only candidate card tags supplied with that rule. `card_tags: []` is correct when none genuinely supports the exact rule. Do not broaden or rewrite the rule.

## Deterministic feedback from a prior invalid rescue result
{{ input.audit_feedback }}

## Rescue items
{{ input.rescue_items }}
