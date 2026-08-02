# Phase 1 — publication census

You are the census model for exactly one publication. Use only `paper.md`,
`metadata.json`, and this prompt. Do not author evidence cards and do not use model
knowledge to add facts absent from the paper.

Walk the complete paper sequentially, including intact tables and footnotes. Record
every gene about which the paper makes a claim, its claim locations, and all touched
categories. Record rule-relevant geneless statements and missing supplementary
values. Do not refuse because a supplement is unavailable.

Write `paper.census.json`. Its `paper_id` must match `metadata.json`.

## Reporting rules

{{REPORTING_RULES}}

## Output schema

```json
{{CENSUS_SCHEMA}}
```

## Exit validation

Check that every section and table is accounted for, every entry has a locator,
genes are valid symbols, IDs and genes are unique, and no rule-covered paper claim
is absent. Repair and repeat, at most three passes. If defects remain, list each one
under `validation_unresolved`; otherwise return an empty list. Return JSON only and
do not claim that Phase 2 has begun.