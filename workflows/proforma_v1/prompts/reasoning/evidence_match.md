# Evidence matching — supplied cards only

Your only task is to match supplied evidence cards to the already-fixed clinical reasoning rules.

Do not change, reinterpret, repair or extend the clinical reasoning. Do not decide whether a rule applies to the patient. Do not generate a diagnosis or PTBG conclusion.

Return one YAML mapping only:

```yaml
assignments:
  - reasoning_id: R1
    card_tags: []
```

Rules:
- Return exactly one assignment row for every supplied reasoning item.
- Use only the supplied `card_tag` values.
- Assign a card only when its supplied content genuinely supports the stated general rule.
- `card_tags: []` is correct when no supplied card supports the rule.
- Do not use patient facts to make a weak card look supportive; patient applicability is audited separately.

## Feedback from a prior evidence-matching attempt
{{ input.audit_feedback }}

## Match pack
The `candidate_cards` list is shared by every item and is supplied once.
{{ input.match_items }}
