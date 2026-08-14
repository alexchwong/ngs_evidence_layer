# Analyse the case against all reporting rules

## Task

Answer every reporting rule using the integrated case and the retrieved evidence, and assign the exact runtime evidence-card tags that directly support each answer.

## Task-specific rules

- Include every rule from `R1.1` through `R5.9` exactly once and in source order.
- Give each rule a self-contained, case-specific answer.
- Use the integrated diagnosis in `case.md`; do not re-adjudicate it.
- Use `evidence.md` as the complete literature-evidence boundary.
- Keep card-level evidence granularity: cite the exact runtime `card_tag` of every evidence card that directly supports the answer.
- Use only tags copied exactly from `evidence.md`; never infer, reconstruct, shorten, or invent a tag.
- Set `citation_status` to `"cited"` when one or more cards directly support the answer and include those tags.
- Set `citation_status` to `"no_citation_required"` with `card_tags: []` when no literature citation is required. This explicit state is compulsory; an empty tag array alone is not sufficient.
- Use a drafting instruction such as `Omit ...` when a rule has no reportable implication.
- Do not add headings, commentary, or fields outside the required JSON shape.

## Output contract

Return JSON only with this shape:

```json
{
  "schema_version": "1.0",
  "answers": [
    {
      "rule_id": "R1.1",
      "text": "Patient-specific conclusion or drafting instruction.",
      "citation_status": "cited",
      "card_tags": ["a1b2c3"]
    }
  ]
}
```

## Final check

Before returning, verify privately that every rule appears exactly once, every card tag is copied exactly from `evidence.md`, and every uncited answer explicitly uses `no_citation_required` with an empty tag list.
