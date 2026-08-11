# Phase 5 — post-acceptance supplementation or revision
## Active phase and scope

Active phase: **Phase 5 only** for one already accepted publication.

Read-only inputs:
- `paper.md`
- `metadata.json`
- `paper.census.json`
- `paper.base.final.json`
- `phase5.json`
- `phase5.existing-cards.json`
- `phase5_prompt.md`
- revision mode only: `paper.phase5-targets.json`

Read `phase5.json` first. `mode: additive` uses the existing additive workflow. `mode: revision` may change only the cards locally authorised in `target_card_ids`. Never alter the census. If a requested interpretation requires census expansion, stop that item and tell the user it requires a full re-ingest.

## Additive mode

First ask what interpretation or interpretations the user believes this paper supports but the accepted cards missed.
For each requested interpretation:
1. search `phase5.existing-cards.json` semantically for the same or materially similar interpretation;
2. if the target publication already contains an equivalent card, show its `card_id` and interpretation and do not create a duplicate;
3. if only another publication contains a similar card, mention it as context but still assess whether this target paper independently supports the requested interpretation;
4. reread `paper.md` specifically for the requested interpretation;
5. if unsupported, say so and do not create a card;
6. if supported, propose one or more minimal independently useful cards with complete paired source-verbatim evidence bundles.

Accept free-text discussion over any number of turns. The user may request rewording, narrower scope, different evidence, splitting, or deletion of proposed cards.

New cards must follow the exact card/evidence shapes already used in `paper.base.final.json`.
- Preserve source-stated disease, population, treatment, variant-class, threshold, exclusion, analysis and other material qualifiers.
- Use only source-verbatim evidence fragments from `paper.md`.
- Every card must have exactly one evidence bundle.
- Evidence may be `contiguous_text`, `composite_text`, or `table_relation` using the same structure as the accepted package.
- `diseases` records exact source-supported applicability only.
- `disease_ancestors` must follow the same canonical values used by the existing accepted package.
- New `card_id` values must use the publication's existing ID pattern and the next unused numeric suffix. Never renumber existing cards.
- Do not create an exact or semantic duplicate of another card from the same publication.

When the user indicates the additions are ready for audit, write exactly `paper.phase5-provisional.json` using the existing ingestion-package shape containing only proposed new cards/evidence. Set `paper_id` from the accepted package, `round` to `1`, `extraction_model` to this model's exact identity, publication type fields equal to the accepted package except `publication_type_verified_by_phase3: false`, `census_entries` equal to `paper.census.json`, coverage fields to exact unions of the proposed cards, and `audit: null`.

A different model reviews the provisional using `phase5_review_prompt.md`. If any card fails, discuss it with the user; any changed card/evidence requires a new independent review. On user `FINALIZE`, require all cards to pass, merge only the reviewed additions into `paper.base.final.json`, preserve existing cards/evidence and audit metadata, append passing audit results for the new cards, and return exactly `paper.final.json`.

## Revision mode — interactive authoring

Revision mode is selected locally with `prepare_phase5.py --key <publication-key> --cards 0001,0003,...`.

At the start:
1. read `paper.phase5-targets.json`;
2. present each selected card by short ID, interpretation and current evidence locator;
3. ask the user what they want changed;
4. discuss the requested revisions interactively over as many turns as needed.

The selected cards are an **allowlist**, not a requirement to modify every selected card. A revision provisional contains only cards that the user actually wants changed.

For each proposed revision:
- reread the source specifically for the requested correction;
- explain briefly when the requested change is not source-supported;
- preserve material qualifiers;
- use only source-verbatim evidence fragments from `paper.md`;
- keep these card fields unchanged: `card_id`, `genes`, `diseases`, `disease_ancestors`, `category`, `evidence_tier`, `secondary_citation`;
- `interpretation`, `locator`, and the paired evidence bundle may change;
- if a structural field needs changing, tell the user to perform a full re-ingest instead.

When the user sends `PROVISIONAL` on its own line, write exactly `paper.phase5-provisional.json` in this revision shape:

```json
{
  "schema_version": "1.0",
  "phase": 5,
  "mode": "revision",
  "publication_key": "<from phase5.json>",
  "paper_id": "<from paper.phase5-targets.json>",
  "round": 1,
  "extraction_model": "<this model's exact identity>",
  "revisions": [
    {
      "card_id": "<full accepted card_id>",
      "replacement_card": {},
      "replacement_evidence": {},
      "revision_sha256": "<revision_sha256(replacement_card, replacement_evidence)>"
    }
  ]
}
```

Before returning the file, execute the embedded `validate_revision_provisional(...)` code below against `phase5.json`, `paper.phase5-targets.json`, the provisional, and `paper.md`. If there are errors, fix the provisional and rerun until it passes. Return the validated provisional only.

## Revision mode — independent review return

Phase 5R is LLM-only and non-interactive. The user will later upload `paper.phase5-review.json` from the independent reviewer into this same Phase 5 conversation.

On receipt:
1. execute `validate_revision_review(...)` using the current provisional;
2. do not accept a review whose per-card `revision_sha256` differs from the current provisional;
3. if any card fails, explain the review criticism to the user and resume interactive revision;
4. after any revision change, generate a new complete provisional and require a fresh Phase 5R review of the batch.

## Revision mode — FINALIZE

Treat all revision discussion as provisional until the user sends `FINALIZE` on its own line.

On `FINALIZE`, require a valid review in which every provisional revision passes. Do **not** create or edit `paper.final.json`.

Write exactly `paper.phase5-revision.json`:

```json
{
  "schema_version": "1.0",
  "phase": 5,
  "mode": "revision",
  "operation": "revise_cards",
  "publication_key": "<from phase5.json>",
  "paper_id": "<from provisional>",
  "base_final_sha256": "<from phase5.json>",
  "base_census_sha256": "<from phase5.json>",
  "extraction_model": "<from provisional>",
  "reviewer_model": "<from review>",
  "revisions": [
    {
      "card_id": "...",
      "replacement_card": {},
      "replacement_evidence": {},
      "revision_sha256": "..."
    }
  ]
}
```

The `revisions` array must be an exact copy of the reviewed provisional revisions. Execute `validate_revision_asset(...)`. If errors occur, fix the asset and rerun. Return the validated `paper.phase5-revision.json` only. Do not claim that accepted corpus state has changed; local `apply_phase5.py` and `confirm.py` are authoritative.

### Source disease alias policy

{{SOURCE_DISEASE_ALIAS_POLICY}}

## Embedded revision validation code

Execute this code; do not paraphrase or reimplement it.

```python
{{PHASE5_CHAT_VALIDATION}}
```
