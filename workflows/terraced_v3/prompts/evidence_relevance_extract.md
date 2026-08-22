# Relevant evidence extraction

Question: {{question}}

Select the card blocks that may be relevant to answering the question for this patient.

Each line is numbered. Return only the line number of each relevant card's opening `<<<CARD nn>>>` header. Python will extract the complete original card block.

Rules:
- select the opening header line only, not interpretation/body line numbers;
- prefer inclusion when uncertain;
- return at most {{max_cards}} card header line numbers;
- do not copy, summarize, rewrite, merge, or invent card text;
- if no supplied card may be relevant, return exactly `NO_RELEVANT_CARDS`.

Return YAML only:
```yaml
relevant_card_header_lines:
  - 1
  - 10
```

# Patient context
```json
{{case}}
```

# Additional task context
{{task_context}}

# Candidate card blocks
{{cards}}
