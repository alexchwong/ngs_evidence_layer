# Phase 5 — post-acceptance supplementation

## Active phase and scope

Active phase: **Phase 5 only**. This is an additive re-ingest of one already accepted publication.

Read-only inputs:
- `paper.md`
- `metadata.json`
- `paper.census.json`
- `paper.base.final.json`
- `phase5.json`
- `phase5.existing-cards.json`
- `phase5_prompt.md`

Do not alter or delete any existing accepted card or evidence bundle. Do not alter the census. If a requested interpretation requires a gene/category not represented by the existing census, stop that item and tell the user it requires a full re-ingest.

## Initial interaction

First ask the user what interpretation or interpretations they believe this paper supports but the accepted cards missed.

For each requested interpretation:
1. search `phase5.existing-cards.json` semantically for the same or materially similar interpretation;
2. if the target publication already contains an equivalent card, show its `card_id` and interpretation and do not create a duplicate;
3. if only another publication contains a similar card, mention it as context but still assess whether this target paper independently supports the requested interpretation;
4. reread `paper.md` specifically for the requested interpretation;
5. if unsupported, say so and do not create a card;
6. if supported, propose one or more minimal independently useful cards with complete paired source-verbatim evidence bundles.

Accept free-text discussion over any number of turns. The user may request rewording, narrower scope, different evidence, splitting, or deletion of proposed cards.

## Carding rules

New cards must follow the exact card/evidence shapes already used in `paper.base.final.json`.

- Preserve source-stated disease, population, treatment, variant-class, threshold, exclusion, analysis and other material qualifiers.
- Use only source-verbatim evidence fragments from `paper.md`.
- Every card must have exactly one evidence bundle.
- Evidence may be `contiguous_text`, `composite_text`, or `table_relation` using the same structure as the accepted package.
- `diseases` records exact source-supported applicability only.
- `disease_ancestors` must follow the same canonical values used by the existing accepted package.
- New `card_id` values must use the publication's existing ID pattern and the next unused numeric suffix. Never renumber existing cards.
- Do not create an exact or semantic duplicate of another card from the same publication.

### Source disease alias policy

A source-stated disease may ground a canonical card disease when it exactly
matches one of these reviewed aliases (case-insensitive):

- `clonal haematopoiesis` → `CHIP`
- `clonal haemopoiesis` → `CHIP`

Emit only the canonical target in `diseases`, but preserve the source's
actual disease or population wording in evidence and interpretation. Alias
matching is otherwise exact. Do not use fuzzy matching, stemming, punctuation
substitution, semantic inference, or nearest-term mapping. A source term that is
neither canonical nor listed above remains outside the controlled vocabulary.

## Preparing the focused independent review

When the user indicates the proposed additions are ready for audit, write exactly one file: `paper.phase5-provisional.json`.

It is a valid ingestion-package-shaped object containing **only the proposed new cards and their evidence**. Set:
- `paper_id` from the accepted package;
- `round` to `1`;
- `extraction_model` to this model's exact identity;
- `publication_type` and `publication_type_basis` equal to the accepted package;
- `publication_type_verified_by_phase3` to `false`;
- `census_entries` equal to `paper.census.json`;
- `genes_covered` and `diseases_covered` to the exact unions represented by the proposed cards;
- `audit` to `null`.

Do not write `paper.final.json` yet. A different model must review the provisional additions using `phase5_review_prompt.md`, producing `paper.phase5-review.json`.

If the review contains any failed card, discuss it with the user. Any change to a reviewed card or evidence invalidates that review: rewrite `paper.phase5-provisional.json` and require a new independent Phase 5 review before finalization.

## FINALIZE

Treat all discussion and candidate cards as provisional until the user sends `FINALIZE` on its own line.

On `FINALIZE`:
- require `paper.phase5-review.json`;
- require every proposed Phase 5 card to have a passing review result;
- require the review model to differ from the Phase 5 extraction model;
- require the reviewed provisional cards/evidence to be unchanged since review;
- merge the reviewed new cards/evidence into `paper.base.final.json` without modifying existing cards/evidence;
- recompute `genes_covered` and `diseases_covered`;
- preserve all existing top-level final-package fields and existing audit metadata;
- preserve all existing audit results and append one `{ "card_id": ..., "verdict": "pass" }` result for each new card;
- write exactly `paper.final.json`.

Do not modify `phase5.json`, `paper.base.final.json`, `paper.base.census.json`, or `paper.census.json`.


After `FINALIZE`, return exactly `paper.final.json`. Do not claim acceptance; `confirm.py` is the deterministic source-aware acceptance gate and will reject any malformed or non-additive result.
