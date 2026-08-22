# Relevant evidence extraction

Question: {{question}}

{{pass_instruction}}

Select the supplied card blocks that may be relevant to answering the question for this patient.

Each card block has a local ID in its opening header, for example `<<<CARD 03>>>`. Return only those `CARD nn` IDs. Python will extract the complete original card blocks and resolve them deterministically.

Rules:
- copy the local `CARD nn` ID exactly from the opening card header;
- prefer inclusion when uncertain;
- return at most {{max_cards}} card IDs in this pass;
- zero cards is valid: return `relevant_card_ids: []` when no supplied card may be relevant;
- do not copy, summarize, rewrite, merge, or invent card text;
- do not emit runtime `[card:...]` tags.

Return YAML only:
```yaml
relevant_card_ids:
  - CARD 03
  - CARD 11
```

Or, when none are relevant:
```yaml
relevant_card_ids: []
```

# Patient context
```json
{{case}}
```

# Additional task context
{{task_context}}

# Candidate card blocks
{{cards}}
