# Phase 5 — focused independent review

## Active phase and output contract

You are the independent Phase 5 reviewer. This phase is **LLM-only and non-interactive**: do not ask the user questions, request clarification, or propose an interactive workflow. Review the supplied artefacts and return exactly one file: `paper.phase5-review.json`.

Read `paper.phase5-provisional.json` first.

## Shared card standards

### Card evidence contract

Every card must have exactly one evidence bundle. The bundle must directly support
every material assertion in the interpretation using source-verbatim fragments from
the paper. A locator is navigation metadata, not evidence.

Preserve every material disease, population, treatment, comparator, variant class,
allelic state, threshold, branch, exclusion, analysis, classifier, certainty, and
other qualifier stated by the source. Do not use a bibliographic reference-list entry,
a heading alone, unsupported nearby text, or model knowledge as substantive evidence.
For germline content, distinguish established inherited or constitutional status from
possible constitutional origin and from a recommendation or indication for germline
work-up; a work-up recommendation supports only a conditional interpretation.

Use `contiguous_text` when one coherent contiguous passage is sufficient. Its sole
fragment has role `claim` and may contain multiple contiguous sentences. Start with
the explicit role claim and expand backward or forward as needed to capture antecedents,
scope, population, treatment, comparator, analysis, thresholds, exclusions, direction,
or clinical consequence. Treat contrast words, exceptions, thresholds, unresolved
pronouns, subgroup distinctions, and a following sentence that changes clinical meaning
as boundary warnings. Stop only when the fragment supports every material element of
the interpretation without relying on unquoted context.

Use `composite_text` only when no single coherent passage contains the minimal
sufficient evidence. Use two to six independently verbatim fragments. One or more
`claim` fragments may jointly support one source assertion; add `scope_heading`,
`legend`, or `footnote` fragments only when they provide necessary governing context.
Every fragment must contribute material support recorded in `support_map`. All
fragments must have compatible disease, population, treatment, comparator, analysis,
and classifier scope. Do not combine separate findings, populations, analyses,
classifier branches, or independently useful conclusions merely because they mention
the same gene. Removing any fragment must leave a material assertion unsupported or
underqualified; otherwise use `contiguous_text`, narrow the interpretation, split the
card, or omit it.

A `scope_heading` is valid only when the substantive passage occurs within that
heading's section and no intervening heading changes scope. A heading supplies context;
it does not establish a role claim by itself.

Use `table_relation` when a table value cannot be interpreted defensibly without its
governing labels. Quote each required `column_header`, `row_header`, `cell`, `legend`,
and `footnote` as a separate fragment. Every relation must identify one value fragment,
all applicable row and column headers, and any marked legend or footnote. Preserve
spanning or multi-level headers. Omit the card when merged cells, continuation rows,
conversion damage, or missing markers leave the relation ambiguous. Do not replace
source labels with model-authored key/value facts.

Before finalizing a card, decompose its interpretation into atomic assertions and map
each material assertion to explicit source words in `support_map`, including gene or
alteration class, disease, population, role and direction, treatment or analysis
context, comparator, certainty, thresholds, branches, and exclusions when applicable.
If any assertion lacks support, expand the bundle, narrow the interpretation, split the
card, or omit it. Once sufficient evidence is assembled, do not shorten it merely for
concision.

### Card utility gate

A card must support a distinct, clinically useful sentence that could materially
contribute to a concise NGS report.

- Create or retain at most one card for each independently useful, directly supported
  role from this publication.
- Do not create or retain a material duplicate of another card from the same
  publication.
- Gene presence, mutation frequency, co-occurrence, enrichment, an entity name,
  molecular mechanism, fusion-partner list, or census category does not by itself
  establish a diagnostic, prognostic, treatment, biomarker, or germline role.
- Do not infer prognosis from frequency, treatment from a kinase or fusion list,
  germline status from tumour findings, or biomarker utility from a diagnostic claim.
- Diagnosis and biomarker cards may coexist only when the biomarker card states a
  distinct source-supported testing target, detection strategy, assay limitation,
  monitoring use, or discrimination use.

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
- satisfies the shared evidence contract and utility gate;
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
