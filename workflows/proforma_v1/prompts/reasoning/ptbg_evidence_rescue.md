# PTBG atomic evidence rescue

## Output serialization contract
Return exactly one YAML mapping conforming to the declared schema. Return YAML only: no Markdown headings, no tables, no prose outside the mapping, no code fence around the answer, and no `---` document separators. The example below shows serialization/shape only; replace placeholders with your actual answer.

```yaml
assignments:
  - rule_id: <exact supplied rule_id>
    card_tags: []
```

For every supplied literature rule that lacks a valid owner assignment, select zero or more genuinely supporting candidate cards. Any `direct_requirement` is part of the literature rule and must also be supported by the selected card.

Return one assignment row for every supplied rule. Use an empty card_tags list when none of the supplied cards supports the exact rule. Do not assess patient applicability and do not rewrite the rule.

## Deterministic feedback from a prior invalid rescue artifact
{{ input.audit_feedback }}

## Rescue items
{{ input.rescue_items }}
