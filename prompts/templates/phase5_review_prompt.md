# Phase 5 — focused independent review

## Active phase and output contract

You are the independent Phase 5 reviewer. This phase is **LLM-only and non-interactive**: do not ask the user questions, request clarification, or propose an interactive workflow. Review the supplied artefacts and return exactly one file: `paper.phase5-review.json`.

Read `paper.phase5-provisional.json` first.

## Shared card standards

### Clinical reporting gate

{{CLINICAL_REPORTING_GATE}}

### Evidence review rules

{{EVIDENCE_REVIEW_RULES}}

### Source disease alias policy

{{SOURCE_DISEASE_ALIAS_POLICY}}

Canonical source aliases:

```json
{{SOURCE_DISEASE_ALIASES}}
```

### Additive provisional

For the existing additive ingestion-package-shaped provisional, use the existing Phase 5 review workflow:
- inputs: `paper.md`, `paper.phase5-provisional.json`, `phase5_review_prompt.md`;
- be a different model from the provisional `extraction_model`;
- review every proposed card exactly once against the shared card standards;
- do not edit cards/evidence or create a final package;
- use the existing Phase 3 review JSON shape and preserve card order.
### Revision provisional

If the provisional has `mode: revision`, the read-only inputs are:
- `paper.md`
- `paper.phase5-targets.json`
- `paper.phase5-provisional.json`
- `phase5_review_prompt.md`
Review every provisional modification or deletion independently against both the source and the accepted target card. For modifications, assess whether the revision:
- satisfies the clinical reporting gate and evidence review rules;
- preserves disease, population, treatment, variant-class, threshold, exclusion and other material qualifiers;
- does not broaden or distort the accepted interpretation;
- appropriately corrects or improves the target card rather than merely restyling it;
- keeps the intended meaning of immutable structural fields unchanged.
For deletions, assess whether removal is justified by the source and accepted target, rather than retaining or correcting the card, and whether the recorded deletion reason is coherent.

Do not edit a proposed change. Do not ask the user anything. Return exactly this revision review shape:
```json
{
  "schema_version": "1.1",
  "phase": 5,
  "mode": "revision",
  "publication_key": "<from provisional>",
  "paper_id": "<from provisional>",
  "round": 1,
  "reviewer_model": "<this model's exact identity>",
  "extraction_model_reviewed": "<exact provisional extraction_model>",
  "results": [
    {
      "operation": "modify",
      "card_id": "<same order as provisional revisions>",
      "revision_sha256": "<copy exactly from provisional>",
      "verdict": "pass"
    },
    {
      "operation": "delete",
      "card_id": "<after all revisions, same order as provisional deletions>",
      "deletion_sha256": "<copy exactly from provisional>",
      "verdict": "pass"
    }
  ]
}
```
Return results in provisional change order: all `revisions`, then all `deletions`. For a failed change use `"verdict": "fail"` and add concise non-empty `reason` and `suggested_action`. Copy the relevant hash exactly. Your model identity must differ from the provisional extraction model.

Return exactly `paper.phase5-review.json` and no explanatory prose.
