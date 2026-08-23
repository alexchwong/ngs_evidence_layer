# Report sentence omit / split / merge plan

Review ALL evidence-resolved atomic reportable statements in one pass.

For every statement choose exactly one disposition:
- `include`: retain as one semantic part;
- `omit`: omit only when all material information is safely represented elsewhere; give a reason;
- `split`: divide a non-atomic statement into two or more faithful semantic parts.

Prefer the FEWEST clinically readable sentences that preserve every material proposition. Non-redundant same-category statements may and often should be merged when scope, polarity, framework, treatment context, and uncertainty remain clear.

Use the same `group` label for parts to be merged. Do not merge across categories unless the supplied workflow policy explicitly permits it. Do not write final combined prose or reason about citations.

Return YAML only:
```yaml
dispositions:
  - statement_id: S0001
    decision: include
    reason: null
parts:
  - statement_id: S0001
    group: G01
    split_text: null
```
