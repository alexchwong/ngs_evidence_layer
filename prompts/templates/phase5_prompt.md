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
Read `phase5.json` first. `mode: additive` uses the existing additive workflow. `mode: revision` may change only the cards locally authorised in `target_card_ids`. Never alter the census. In additive mode, first match each requested interpretation to one or more existing census claims. A census claim is a review boundary, not proof that a card should exist. If no existing census claim covers the requested interpretation, stop that item and tell the user it requires a full re-ingest.

## Shared card standards

### Clinical reporting gate

{{CLINICAL_REPORTING_GATE}}

### Card content rules

{{CARD_CONTENT_RULES}}

### Evidence bundle rules

{{EVIDENCE_BUNDLE_RULES}}

### Source disease alias policy

{{SOURCE_DISEASE_ALIAS_POLICY}}

Canonical source aliases:

```json
{{SOURCE_DISEASE_ALIASES}}
```

## Additive mode
First ask what interpretation or interpretations the user believes this paper supports but the accepted cards missed.
For each requested interpretation:
1. identify the matching claim or claims in `paper.census.json`; if none match, require full re-ingest and stop that item;
2. search `phase5.existing-cards.json` semantically for the same or materially similar interpretation;
3. if the target publication already contains an equivalent card, show its `card_id` and interpretation and do not create a duplicate;
4. if only another publication contains a similar card, mention it as context but still assess whether this target paper independently supports the requested interpretation;
5. reread `paper.md` specifically for the requested interpretation;
6. if unsupported, say so and do not create a card;
7. if supported, propose one or more cards satisfying the shared card standards above.
Accept free-text discussion over any number of turns. The user may request rewording, narrower scope, different evidence, splitting, or deletion of proposed cards.
New cards must follow the exact card/evidence shapes already used in `paper.base.final.json`.
- `diseases` records exact source-supported applicability only.
- `disease_ancestors` must follow the same canonical values used by the existing accepted package.
- New `card_id` values must use the publication's existing ID pattern and the next unused numeric suffix. Never renumber existing cards.
When the user indicates the additions are ready for audit, write exactly `paper.phase5-provisional.json` using the existing ingestion-package shape containing only proposed new cards/evidence.
Set `paper_id` from the accepted package, `round` to `1`, `extraction_model` to this model's exact identity, publication type fields equal to the accepted package except `publication_type_verified_by_phase3: false`, `census_entries` equal to `paper.census.json`, coverage fields to exact unions of the proposed cards, and `audit: null`.
A different model reviews the provisional using `phase5_review_prompt.md`. If any card fails, discuss it with the user; any changed card/evidence requires a new independent review.

When the user sends `FINALIZE` on its own line, require all cards to pass, then show the exact pending change set using short card IDs:
- `ADD: 000x,...`
- `DELETE: none`
- `MODIFY: none`
Do **not** write `paper.final.json` yet. Ask the user to send `CONFIRM CHANGES` on its own line. Only after that exact confirmation, and only if the reviewed provisional has not changed, merge only the reviewed additions into `paper.base.final.json`, preserve existing cards/evidence and audit metadata, append passing audit results for the new cards, and return exactly `paper.final.json`. Any change after review or confirmation requires a fresh review and confirmation.
## Revision mode — interactive authoring

Revision mode is selected locally with `prepare_phase5.py --key <publication-key> --cards 0001,0003,...` or `--cards all`. `--cards all` releases every accepted card from this publication into the revision allowlist.
At the start:
1. read `paper.phase5-targets.json`;
2. present each selected card by short ID, interpretation and current evidence locator;
3. ask the user what they want changed;
4. discuss the requested revisions interactively over as many turns as needed.
The selected cards are an **allowlist**, not a requirement to change every selected card. During Phase 5 the user chooses the actual subset to modify or delete. A revision provisional contains only those actual changes. Revision mode does not add cards; use additive Phase 5 for additions.
For each proposed modification:
- reread the source specifically for the requested correction;
- explain briefly when the requested change is not source-supported;
- require the replacement interpretation and evidence to satisfy the shared card standards;
- keep these card fields unchanged: `card_id`, `genes`, `diseases`, `disease_ancestors`, `category`, `evidence_tier`, `secondary_citation`;
- `interpretation`, `locator`, and the paired evidence bundle may change;
- if a structural field needs changing, tell the user to perform a full re-ingest instead.
For each proposed deletion:
- delete only an authorised target card;
- record a concise reason agreed with the user;
- the deletion removes the accepted card, its paired evidence bundle, and its matching final audit result;
- do not use deletion to rename/restructure a card that should instead undergo full re-ingest.

When the user sends `PROVISIONAL` on its own line, write exactly `paper.phase5-provisional.json` in this revision shape:
```json
{
  "schema_version": "1.1",
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
  ],
  "deletions": [
    {
      "card_id": "<full accepted card_id>",
      "reason": "<concise user-agreed reason>",
      "deletion_sha256": "<deletion_sha256(card_id, prepared card hash, prepared evidence hash, reason)>"
    }
  ]
}
```
`revisions` and `deletions` may each be empty, but at least one actual change is required. A card cannot appear in both arrays.

Before returning the file, execute the embedded `validate_revision_provisional(...)` code below against `phase5.json`, `paper.phase5-targets.json`, the provisional, and `paper.md`. If there are errors, fix the provisional and rerun until it passes. Return the validated provisional only.
## Revision mode — independent review return

Phase 5R is LLM-only and non-interactive. The user will later upload `paper.phase5-review.json` from the independent reviewer into this same Phase 5 conversation.
On receipt:
1. execute `validate_revision_review(...)` using the current provisional;
2. do not accept a review whose per-change hash differs from the current provisional;
3. if any modification or deletion fails, explain the review criticism to the user and resume interactive revision;
4. after any revision change, generate a new complete provisional and require a fresh Phase 5R review of the batch.
## Revision mode — FINALIZE

Treat all revision discussion as provisional until the user sends `FINALIZE` on its own line.

On `FINALIZE`, require a valid review in which every provisional modification/deletion passes. Do **not** create or edit `paper.final.json` and do **not** write `paper.phase5-revision.json` yet.

Show the exact pending change set using short card IDs:
- `ADD: none`
- `DELETE: 000x,...` or `none`
- `MODIFY: 000x,...` or `none`
Ask the user to send `CONFIRM CHANGES` on its own line. Only after that exact confirmation, and only if the reviewed provisional has not changed, write exactly `paper.phase5-revision.json`:
```json
{
  "schema_version": "1.1",
  "phase": 5,
  "mode": "revision",
  "operation": "change_cards",
  "publication_key": "<from phase5.json>",
  "paper_id": "<from provisional>",
  "base_final_sha256": "<from phase5.json>",
  "base_census_sha256": "<from phase5.json>",
  "extraction_model": "<from provisional>",
  "reviewer_model": "<from review>",
  "revisions": [],
  "deletions": [],
  "confirmed_change_set": {
    "add": [],
    "delete": ["<full deleted card IDs in provisional order>"],
    "modify": ["<full modified card IDs in provisional order>"]
  }
}
```
The `revisions` and `deletions` arrays must be exact copies of the reviewed provisional arrays. `confirmed_change_set` must exactly encode the change set the user just confirmed. Execute `validate_revision_asset(...)`. If errors occur, fix the asset and rerun. Return the validated `paper.phase5-revision.json` only. Do not claim that accepted corpus state has changed; local `apply_phase5.py` and `confirm.py` are authoritative.

## Embedded revision validation code

Execute this code; do not paraphrase or reimplement it.

```python
{{PHASE5_VALIDATION_BUNDLE}}
```
