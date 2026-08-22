# Local card-pairing repair

The statements and reasons below are frozen. Do not rewrite them.
For each statement, select the local CARD labels whose interpretations reasonably support the statement given the patient premises in `reason`.
Use only labels from the supplied candidate card blocks. Use `card_refs: []` when no literature card is appropriate.
Do not invent labels.

Return YAML only:

```yaml
repairs:
  - candidate_id: C1
    card_refs: ["CARD 01"]
```

Return exactly one repair row for every supplied candidate_id.

# Frozen statements
{{statements}}

# Candidate card blocks
{{cards}}
