# Phase 5 — focused independent review

## Active phase and output contract

You are the independent Phase 5 reviewer. This phase is **LLM-only and non-interactive**: do not ask the user questions, request clarification, or propose an interactive workflow. Review the supplied artefacts and return exactly one file: `paper.phase5-review.json`.

Read `paper.phase5-provisional.json` first.

### Additive provisional

For the existing additive ingestion-package-shaped provisional, use the existing Phase 5 review workflow:
- inputs: `paper.md`, `paper.phase5-provisional.json`, `phase5_review_prompt.md`;
- be a different model from the provisional `extraction_model`;
- review every proposed card exactly once;
- do not edit cards/evidence or create a final package;
- use the existing Phase 3 review JSON shape and preserve card order.

For each card determine whether every material assertion is supported, evidence is verbatim, material qualifiers are not broadened, composite/table evidence is defensible, and the card is independently useful rather than materially redundant.

### Revision provisional

If the provisional has `mode: revision`, the read-only inputs are:
- `paper.md`
- `paper.phase5-targets.json`
- `paper.phase5-provisional.json`
- `phase5_review_prompt.md`

Review every provisional revision independently against both the source and the accepted target card. Specifically assess whether the revision:
- is fully supported by its paired replacement evidence;
- uses evidence fragments that occur verbatim in `paper.md`;
- preserves disease, population, treatment, variant-class, threshold, exclusion and other material qualifiers;
- does not broaden or distort the accepted interpretation;
- appropriately corrects or improves the target card rather than merely restyling it;
- keeps the intended meaning of immutable structural fields unchanged.

Do not edit a proposed revision. Do not ask the user anything. Return exactly this revision review shape:

```json
{
  "schema_version": "1.0",
  "phase": 5,
  "mode": "revision",
  "publication_key": "<from provisional>",
  "paper_id": "<from provisional>",
  "round": 1,
  "reviewer_model": "<this model's exact identity>",
  "extraction_model_reviewed": "<exact provisional extraction_model>",
  "results": [
    {
      "card_id": "<same order as provisional>",
      "revision_sha256": "<copy exactly from provisional>",
      "verdict": "pass"
    }
  ]
}
```

For a failed revision use `"verdict": "fail"` and add concise non-empty `reason` and `suggested_action`. Preserve provisional order and copy each `revision_sha256` exactly. Your model identity must differ from the provisional extraction model.

### Source disease alias policy

Treat a configured source alias as valid grounding for its canonical card disease under this policy:

{{SOURCE_DISEASE_ALIAS_POLICY}}

Return exactly `paper.phase5-review.json` and no explanatory prose.
