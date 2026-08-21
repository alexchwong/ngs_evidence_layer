# Diagnosis-lab report evidence alignment

For each immutable report `fact` + `reason` pair, identify which supplied runtime card tag or tags, if any, directly support the stated reason at the stated classifier, disease, context, and strength.

Return the same YAML document and preserve every existing value character-for-character. Add only one field named `citation` to each fact row.

Example:

```yaml
facts:
  - fact_id: diagnosis-summary-1
    fact: "..."
    reason: "..."
    source_case_fact_ids: [F1]
    source_diagnostic_ids: [D1-WHO5, DX-FINAL-F1]
    citation: "[card:abcdef]"
  - fact_id: diagnosis-summary-2
    fact: "..."
    reason: "..."
    source_case_fact_ids: []
    source_diagnostic_ids: [DX-FINAL-U1]
    citation: null
```

Rules:
- Include every supplied fact exactly once and preserve the supplied order.
- Preserve `fact_id`, `fact`, `reason`, `source_case_fact_ids`, and `source_diagnostic_ids` character-for-character.
- Use only exact runtime card tags from the supplied permitted evidence.
- Multiple directly supporting cards may be written as adjacent tags, for example `[card:abcdef][card:123456]`.
- If no card directly supports the complete reason at its stated strength, use `citation: null`; this is valid for patient observations, source-derived limitations, and routing statements.
- Match evidence to the reason, not merely to a shared gene name.
- Do not use a WHO5 card to support an ICC-specific claim, or an ICC card to support a WHO5-specific claim, unless the card itself directly supports both.
- Do not rescue a claim with a vaguely related card.
- Do not change, soften, expand, delete, merge, or split any supplied content.
- Do not search for new evidence or write prose outside the YAML object.