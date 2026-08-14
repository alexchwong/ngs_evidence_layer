# Analyse the case against all reporting rules

## Task

Answer every reporting rule using the integrated case and the retrieved evidence, and assign the exact runtime evidence-card tags that directly support each answer.

## Task-specific rules

- Include every rule from `R1.1` through `R5.9` exactly once and in source order.
- Write exactly one line per rule. Do not add headings, bullets, blank lines, code fences, commentary, or other content.
- Begin each line with the exact rule ID followed by one space.
- Give each rule a self-contained, case-specific answer on that same line.
- Use the integrated diagnosis in `case.md`; do not re-adjudicate it.
- Use `evidence.md` as the complete literature-evidence boundary.
- Keep card-level evidence granularity: cite every evidence card that directly supports the answer using its exact runtime `card_tag`.
- Use only tags copied exactly from `evidence.md`; never infer, reconstruct, shorten, or invent a tag.
- End every line with exactly one citation disposition:
  - one or more adjacent runtime markers, e.g. `[card:a1b2c3][card:d4e5f6]`; or
  - the exact literal `(no citation required)` when no literature citation is required.
- A line without a terminal citation disposition is invalid. Never leave the citation state implicit.
- Card markers are allowed only as the terminal suffix. Do not place `[card:...]` inside answer prose.
- Do not combine card markers with `(no citation required)` on the same line.
- Do not repeat the same card marker on one rule.
- Use a drafting instruction such as `Omit ...` when a rule has no reportable implication.

## Validation repair

If deterministic validation reports a citation-tag failure:

- repair only the affected rule(s);
- inspect/edit the current `report-draft.md`;
- `evidence.md` is the only source file you may read or re-read during citation repair;
- locate the supporting statement in `evidence.md` and copy its exact runtime `card_tag`;
- do not read or re-read `case.md`, `rules/agreed_reporting_rules.md`, `card-tags.json`, `bundle.json`, `diagnostic_evidence.md`, `adjudication.json`, `cards/`, the corpus/index, the original case document, or any other source file;
- never derive a runtime tag from a stable card ID or from `card-tags.json`.

Do not change unaffected rule answers merely because validation failed elsewhere.

## Output contract

Return Markdown only in this exact line grammar:

```text
R1.1 Patient-specific conclusion. [card:a1b2c3]
R1.2 Patient-specific conclusion supported by two cards. [card:a1b2c3][card:d4e5f6]
R1.3 Omit this topic because it has no reportable implication. (no citation required)
```

Continue in exact source order through `R5.9`.

## Final check

Before returning, verify privately that there is exactly one line for every rule, every line has a terminal citation disposition, every card tag is copied exactly from `evidence.md`, and no citation marker appears inside answer prose.
