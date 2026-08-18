# Evidence alignment

For each final `fact` + `reason` pair, identify which supplied runtime card tag(s), if any, directly support the stated reason at the stated disease/context/strength.

Return the same category document and preserve every non-citation value character-for-character. For diagnosis, preserve `provisional_cmcs` and `diagnoses` exactly. Preserve every fact in the same order and add only a third field named `citation` to each fact/reason pair.

Example:

```yaml
- fact: "..."
  reason: "..."
  citation: "[card:abcdef]"
- fact: "..."
  reason: "..."
  citation: null
```

Rules:
- Use only exact runtime card tags from the supplied category evidence.
- Multiple directly supporting cards may be written as adjacent tags, e.g. `[card:abcdef][card:123456]`.
- If no card directly supports the reason, use `citation: null`. This is not automatically an error.
- Do not rescue a claim with a vaguely related card.
- Do not change, soften, expand or delete the fact or reason in this pass.
- Return YAML only.
