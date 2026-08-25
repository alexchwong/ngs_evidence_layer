# Terraced-v2 domain evidence alignment

Add evidence dispositions to the supplied immutable final domain state. Do not revise its clinical content.

Return YAML only with exactly:

```yaml
facts:
  - fact: "<copied exactly>"
    reason: "<copied exactly>"
    citation: "[card:0123456789ab]"
uncertainties:
  - uncertainty: "<copied exactly>"
    reason: "<copied exactly>"
    citation: null
```

Rules:
- Include every supplied fact and uncertainty exactly once and in supplied order.
- Preserve all supplied text character-for-character.
- `citation` is either null or one or more adjacent exact runtime card tags supplied in the evidence.
- Cite only evidence that directly supports the complete reason at its stated strength.
- Patient observations and case-derived limitations may correctly have `citation: null`.
- Do not add, remove, merge, split, soften or strengthen any clinical content.
- Do not write `upstream_issues` into this artifact; they remain audit-only review flags.
