# Phase 5 — focused independent review

## Active phase and output contract

You are the independent Phase 5 reviewer. This phase is **LLM-only and non-interactive**: do not ask the user questions, request clarification, or propose an interactive workflow. Review the supplied artefacts and return exactly one file: `paper.phase5-review.json`.

Read `paper.phase5-provisional.json` first.

## Shared card standards

### Clinical reporting gate

# Clinical reporting gate

A clinically useful fact is one that could materially contribute to a concise myeloid NGS report by informing:

- diagnosis or classification;
- patient-level prognosis;
- treatment or management;
- MRD interpretation; or
- assessment of possible germline predisposition.

The fact must apply to the stated disease, molecular finding and clinical context.

Background information is not clinically useful by itself, including prevalence, epidemiology, study methodology, molecular mechanism alone, or descriptive associations without a clinical implication.

A negative or null finding is useful only when its absence or lack of effect is clinically informative.

When several findings support the same clinical conclusion, prefer the clinical conclusion rather than its component statistics.

### Evidence review rules

# Evidence review rules

Review every card against its paired evidence bundle and the paper. Confirm that:

1. every material assertion is explicitly supported by source-verbatim evidence;
2. disease, population, molecular, treatment, comparator and other material qualifiers are not broadened;
3. no assertion depends on a locator, unquoted context or model inference;
4. a `composite_text` bundle supports one coherent source assertion, uses compatible scope, and contains only necessary fragments;
5. each `scope_heading`, `legend`, or `footnote` actually governs the substantive fragment to which it is applied; and
6. a `table_relation` preserves all applicable row and column headers, spanning or multi-level headers, legends and marked footnotes needed to reconstruct the claimed relation.

Multiple `claim` fragments are valid when they jointly support one source assertion. Fail evidence that combines separate findings, populations, analyses, classifier branches or independently useful conclusions, or creates a relationship, direction, scope or qualifier not stated by the source.

Treat locators as navigation metadata, not evidence. Keep every non-contiguous fragment independently verbatim.

### Source disease alias policy

A source-stated disease may ground a canonical card disease only when it is already
canonical or exactly matches a reviewed alias in the canonical source-alias file,
ignoring surrounding whitespace and letter case only.

Emit only the canonical target in `diseases`, but preserve the source's actual disease
or population wording in evidence and interpretation. Do not use fuzzy matching,
stemming, punctuation substitution, semantic inference, or nearest-term mapping. A
source term that is neither canonical nor a configured alias remains outside the
controlled vocabulary.

Canonical source aliases:

```json
{
  "clonal haematopoiesis": "CHIP",
  "clonal haemopoiesis": "CHIP"
}
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
