# Fact/reason to card evidence alignment

For each supplied surfaced clinical fact, select the evidence card tag(s) that genuinely support the stated reason sufficiently to justify the fact.

Return YAML only:

```yaml
alignments:
  - fact_id: prognosis-V1-DX1
    citation: "[card:0123456789ab]"
```

Rules:
- include every supplied fact_id exactly once in supplied order;
- `citation` is null or one/more adjacent exact supplied runtime card tags;
- candidate tags are hints only: verify them; replace or omit them when inappropriate;
- treat the reason as the semantic bridge: a card must support the reason, and that reason must be sufficient for the fact;
- use only cards supplied for this alignment task and, where a fact is diagnosis-scoped, only cards retrieved for that diagnosis context;
- case-derived facts may correctly receive null;
- do not alter facts, reasons, decisions, IDs, or diagnosis scope;
- do not add commentary.
