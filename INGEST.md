# Ingesting publications

This is the operator guide for adding papers to the NEL corpus.

## Quick start

From the repository root, create the local environment once:

```bash
python3 -m venv .env
. .env/bin/activate
python -m pip install -r requirements.txt
```

Activate it in each new shell, then run the normal ingestion sequence:

```bash
. .env/bin/activate

# Parse source PDFs and resolve any pending citations.
python scripts/parse_pdfs.py --corpus <name> --mailto <email>
python scripts/citations.py request --corpus <name>
python scripts/citations.py apply --corpus <name> --response <file>

# Alternatively, resolve pending citations with a manual worksheet.
python scripts/citations.py manual-export --corpus <name>
python scripts/citations.py manual-apply --corpus <name> --csv <file>

# Create all work folders, or select one paper.
python scripts/fanout.py --corpus <name>
python scripts/fanout.py --corpus <name> --key <publication-key>

# After manually completing Phases 1–4, accept and incorporate the paper.
python scripts/confirm.py --key <publication-key>
python scripts/incorporate.py
python scripts/build_secondary_source_backlog.py
```

Quarantine commands for a paper that must remain outside the corpus:

```bash
# Uses the default reason "Out of scope for the corpus".
python scripts/quarantine.py hold --key <publication-key>
# Override the reason when a more specific explanation is useful.
python scripts/quarantine.py hold --key <publication-key> --reason "<reason>"
python scripts/quarantine.py list
python scripts/quarantine.py review --key <publication-key> --note "<review-note>"
```

Redo commands for re-running an accepted paper from Phase 1 or Phase 2:

```bash
# Redo the census and all downstream cards.
python scripts/prepare_redo.py --key <publication-key> --phase 1

# Keep the accepted census and redo cards/review/adjudication.
python scripts/prepare_redo.py --key <publication-key> --phase 2

# Complete the normal remaining phases, then confirm without --overwrite.
python scripts/confirm.py --key <publication-key>
python scripts/incorporate.py
```

Phase 5 commands for post-acceptance additions or card revisions:

```bash
# Add missed evidence.
python scripts/prepare_redo.py --key <publication-key> --phase 5

# Or inspect the corpus and prepare selected accepted cards for revision.
scripts/render_corpus --list
scripts/render_corpus --key <publication-key> --dest ./temp/corpus
python scripts/prepare_redo.py --key <publication-key> --phase 5 --cards 0001,0003,0005
# Or release every accepted card from the publication into the revision allowlist.
python scripts/prepare_redo.py --key <publication-key> --phase 5 --cards all

# Complete the Phase 5 authoring and independent review steps described below.
# Revision mode: restate exactly the existing cards actually modified/deleted.
python scripts/apply_phase5.py --key <publication-key> --cards 0001,0003
python scripts/confirm.py --key <publication-key>
python scripts/incorporate.py
```

Move all private ingestion state between computers:

```bash
python scripts/transport.py export --output nel-private-state.tar.gz
python scripts/transport.py import nel-private-state.tar.gz --dry-run
python scripts/transport.py import nel-private-state.tar.gz
```

The normal workflow is:

```text
PDF
→ parse
→ DOI/citation curation
→ fanout
→ Phase 1
→ Phase 2
→ Phase 3
→ Phase 4
→ confirm
→ incorporate
→ rebuild secondary-source curation backlog
```

Use a fresh ChatGPT or Claude conversation for each model phase. Phase 3 must use a
different model from Phase 2.

Private source publications and ingestion state live under `pdf/`, `input/`, `work/`,
`quarantine/`, `accept/`, `archive/`, and `curation/`. Do not commit these directories'
contents.

## Setup

From the repository root:

```bash
python3 -m venv .env
. .env/bin/activate
python -m pip install -r requirements.txt
```

## Move private corpus state between computers

`scripts/transport.py` packages the ignored private ingestion directories:
`pdf/`, `input/`, `work/`, `quarantine/`, `accept/`, `archive/`, and `curation/`.
Reproducible committed `output/` artefacts are not included.

Export:

```bash
python scripts/transport.py export --output nel-private-state.tar.gz
```

The archive is compressed but **not encrypted**. Transfer it using an appropriate
private channel.

On the destination computer, inspect the import first:

```bash
python scripts/transport.py import nel-private-state.tar.gz --dry-run
```

Then import:

```bash
python scripts/transport.py import nel-private-state.tar.gz
```

Import adds missing files and skips byte-identical files. If an existing destination
file has different content, the import is refused rather than overwriting it.

## 1. Parse PDFs

Place source PDFs in:

```text
pdf/<corpus>/
```

Use a meaningful PDF filename. Its filename stem becomes the stable `publication_key`
used for work folders and card IDs.

Parse the corpus:

```bash
python scripts/parse_pdfs.py --corpus <name> --mailto <email>
```

Successful PDFs are moved to:

```text
pdf/archive/<corpus>/
```

Parsed Markdown and citation/index state are written under:

```text
input/<corpus>/
```

The model phases use `paper.md` generated from this Markdown path, not the original PDF.

If parsing succeeds but citation metadata cannot be resolved, curate the DOI before
fanout.

## 2. Curate missing DOI/citation metadata

There are two supported paths.

### Model-assisted DOI curation

Create a request for unresolved papers:

```bash
python scripts/citations.py request --corpus <name>
```

This writes a request under:

```text
input/<name>/citations/
```

Give that request to ChatGPT or Claude and ask it to identify the DOI for each listed
paper. Save the resulting JSON response, then apply it:

```bash
python scripts/citations.py apply --corpus <name> --response <file>
```

The script verifies candidate DOIs against Crossref before accepting them.

### Manual DOI curation

Export a worksheet:

```bash
python scripts/citations.py manual-export --corpus <name>
```

Complete the generated CSV, then apply it:

```bash
python scripts/citations.py manual-apply --corpus <name> --csv <file>
```

Do not proceed to fanout until the selected paper has resolved citation metadata.

## 3. Fan out papers

Create one working folder per publication:

```bash
python scripts/fanout.py --corpus <name>
```

Or fan out one paper:

```bash
python scripts/fanout.py --corpus <name> --key <publication-key>
```

Each new paper receives:

```text
work/<publication-key>/
  paper.md
  metadata.json
```

Existing work folders are not modified. Before creating any work folders, `fanout.py`
preflights DOI collisions against accepted and quarantined papers. It refuses a DOI that
is already accepted or belongs to a different quarantined paper, preventing duplicate
ingestion before work begins.

## Quarantine a paper before acceptance

If fanout has occurred but a partially or fully processed paper must not enter the
corpus, move its complete working history out of the active pipeline:

```bash
python scripts/quarantine.py hold \
  --key <publication-key>
```

The default reason is `Out of scope for the corpus`. Supply `--reason "<reason>"` to
record a more specific explanation.

This atomically moves:

```text
work/<publication-key>/
```

to:

```text
quarantine/<publication-key>/
```

The paper's existing phase files are preserved. A `quarantine.json` file records the
reason and timestamp. `confirm.py` only reads `work/`, and `incorporate.py` only reads
`accept/`, so the quarantined paper cannot enter the corpus through the normal workflow.
Subsequent fanout runs recognize the quarantined key and do not recreate it under
`work/`.

List held papers:

```bash
python scripts/quarantine.py list
```

Return a paper to `work/` for further review:

```bash
python scripts/quarantine.py review \
  --key <publication-key> \
  --note "Reconsider after scope-policy update"
```

The complete folder moves back unchanged, including `quarantine.json`; the return event
is appended to its audit history. Resume review from the appropriate existing phase. The
commands refuse to merge or overwrite folders when both source and destination state
exist.

Quarantine is a pre-acceptance action. It refuses papers that already have final or
census state under `accept/`; removing an accepted paper from the corpus requires a
separate withdrawal or corpus-versioning procedure.

## 4. Run Phases 1–4

Run each phase in a fresh chat. Save the model's returned JSON file into the same
`work/<publication-key>/` folder before starting the next phase.

| Phase | Chat/session | Give the model | Prompt | Save output as |
|---|---|---|---|---|
| 1 — census | Fresh ChatGPT or Claude chat | `paper.md`, `metadata.json` | `prompts/phase1_prompt.md` | `paper.census.json` |
| 2 — carding | Fresh chat | `paper.md`, `metadata.json`, `paper.census.json` | `prompts/phase2_prompt.md` | `paper.provisional-001.json` |
| 3 — independent review | Fresh chat using a **different model from Phase 2** | `paper.md`, `paper.provisional-001.json` | `prompts/phase3_prompt.md` | `paper.review-001.json` |
| 4 — human adjudication | Fresh chat | `paper.md`, `metadata.json`, `paper.census.json`, `paper.provisional-001.json`, `paper.review-001.json` | `prompts/phase4_prompt.md` | `paper.final.json` |

### Phase 1 — census

Start a fresh chat and provide exactly:

- `work/<publication-key>/paper.md`
- `work/<publication-key>/metadata.json`
- `prompts/phase1_prompt.md`

Save the output as:

```text
work/<publication-key>/paper.census.json
```

Do not run Phase 2 in the same conversation.

### Phase 2 — carding

Start a fresh chat with:

- `paper.md`
- `metadata.json`
- `paper.census.json`
- `prompts/phase2_prompt.md`

Normally save the output as:

```text
paper.provisional-001.json
```

If Phase 2 instead returns a census critique such as:

```text
paper.census-critique-001.md
```

stop Phase 2. Start a fresh Phase 1 conversation, provide the critique with the Phase 1
inputs, regenerate `paper.census.json`, then start Phase 2 again in a new conversation.
Once a provisional package has been produced, do not repeat Phase 2 after audit.

#### Source disease aliases

Phase 2 normally omits a card when the source-stated disease is outside the closed
evidence-card vocabulary. A small reviewed allowlist in
`schema/disease_vocabulary.json` under `source_disease_aliases` provides explicit
exceptions. For example, source wording `clonal haematopoiesis` or `clonal
haemopoiesis` is stored as canonical disease `CHIP`; the source wording must still be
preserved in the evidence and interpretation.

Aliases are case-insensitive but otherwise exact. They do not enable fuzzy matching,
stemming, punctuation substitution, semantic inference, or mapping to a nearest term.
To add an alias, map the complete source phrase to an existing canonical `diseases`
value, regenerate the affected prompts, and run the full test suite. Do not use aliases
to encode taxonomic ancestry or retrieval relationships; those remain separate
`umbrella` and `retrieval_related` configuration.

### Phase 3 — independent review

Use a **different model** from the one used for Phase 2.

For example:

```text
Phase 2: ChatGPT
Phase 3: Claude
```

Start a fresh chat with exactly:

- `paper.md`
- `paper.provisional-001.json`
- `prompts/phase3_prompt.md`

Do not provide the census, schemas, vocabulary, reporting rules, or another publication.

Save:

```text
paper.review-001.json
```

Phase 3 reviews the proposed cards; it does not edit them and does not create the final
package.

### Phase 4 — human adjudication

Start a fresh chat with:

- `paper.md`
- `metadata.json`
- `paper.census.json`
- `paper.provisional-001.json`
- `paper.review-001.json`
- `prompts/phase4_prompt.md`

Phase 4 presents the cards and review findings for human adjudication. Discuss the cards
with the model and make the final source-supported decisions.

Save the final output as:

```text
paper.final.json
```

## 5. Confirm the paper

After Phase 4 is complete:

```bash
python scripts/confirm.py --key <publication-key>
```

`confirm.py` is the deterministic acceptance gate. If validation fails, nothing is
accepted.

On success it writes the accepted final/census pair under `accept/`, stamps the accepted
package with the current `release/VERSION` as `accepted_in_version`, and moves the full
working history from:

```text
work/<publication-key>/
```

to:

```text
archive/<publication-key>/
```

## 6. Incorporate accepted papers

Rebuild the distributable corpus from accepted papers:

```bash
python scripts/incorporate.py
```

The main outputs are:

```text
output/corpus/nel.corpus.json
output/corpus/nel.index.json
output/reports/build-report.json
```

`incorporate.py` reads from `accept/`. Invalid accepted packages are reported and
excluded; valid accepted papers are incorporated. `nel.index.json` exposes papers by
`accepted_in_version`, allowing corpus additions to be traced to a release.

### Rebuild the secondary-source curation backlog

After incorporation, rebuild the curator backlog from the archived Phase 1–4 audit
history and the current corpus:

```bash
python scripts/build_secondary_source_backlog.py
```

The script looks for provisional cards that:

- Phase 3 marked `fail`;
- were removed from `paper.final.json`; and
- carried a non-null `secondary_citation`.

It groups those removed interpretations by the cited source paper. If the cited source
already exists in the current corpus, that source and its removed cards are excluded
from the outstanding backlog. Matching is conservative: DOI is used when available;
otherwise the normalized title and year must match exactly.

Outputs are private generated curator files:

```text
curation/secondary-source-backlog.json
curation/secondary-source-backlog.md
```

The Markdown file is the human-readable paper-curation queue. Each entry preserves the
removed provisional interpretation, its originating curated paper, and the Phase 3
failure reason and suggested action. The JSON file contains the same information in a
machine-readable form.

The command never modifies `archive/`, `accept/`, or `output/`. `curation/` is ignored
by Git but is included by `transport.py` when moving private corpus state to another
computer.

## 6A. Redo an accepted paper from Phase 1 or Phase 2

Use a full redo when the accepted census or card extraction should be rebuilt rather than
patched with Phase 5. Preparation creates `work/<publication-key>/` and a `redo.json`
marker that authorises replacement of the current Phase 1–4 lineage.

Redo the census and every downstream phase:

```bash
python scripts/prepare_redo.py --key <publication-key> --phase 1
```

Phase 1 preparation restores `paper.md` and `metadata.json`, plus frozen baseline files
used only by local confirmation. Generate a new `paper.census.json`, then continue through
Phases 2–4.

Keep the accepted census and rebuild cards from Phase 2:

```bash
python scripts/prepare_redo.py --key <publication-key> --phase 2
```

Phase 2 preparation additionally restores the accepted `paper.census.json`. The census
must remain equivalent as JSON through confirmation; use `--phase 1` if it needs to
change. `--cards` is not valid for Phase 1 or Phase 2 redo.

Both modes create:

```text
paper.base.final.json
paper.base.census.json
redo.json
```

Do not edit these baseline files or `redo.json`. After completing the remaining normal
phases, confirm normally:

```bash
python scripts/confirm.py --key <publication-key>
```

`confirm.py` detects `redo.json`, verifies that the accepted baseline has not changed since
preparation, validates the complete replacement Phase 1–4 lineage, and replaces the
accepted final/census and current archive. The superseded accepted envelope, census, and
archive are retained under `archive/<publication-key>/redo/NNN/`. Repeated redos therefore
do not require a release-version change. Existing Phase 5 supplement/revision records are
not carried onto the new current lineage; they remain preserved in the redo snapshot.

## 7. Phase 5 — post-acceptance additions and card revisions

Use Phase 5 after a paper has already been accepted. It supports two modes:

- **additive mode** adds evidence-backed cards missed during Phases 1–4;
- **revision mode** modifies or deletes explicitly authorised accepted cards.

Neither mode may change the census. Structural changes to an accepted card's identity or
applicability require a redo from Phase 2, or Phase 1 if the census must also change.

### Browse accepted publications and cards

List publication keys with their citations:

```bash
scripts/render_corpus --list
```

Render one publication's accepted cards to Markdown:

```bash
scripts/render_corpus --key <publication-key> --dest ./temp/corpus
```

This writes `./temp/corpus/<publication-key>.md`. Each card is headed by its short numeric
ID (for example `0001`) so those IDs can be passed directly to `prepare_redo.py --phase 5 --cards`. The
renderer is read-only and uses the committed corpus/index outputs.

### Prepare additive Phase 5

Restore an accepted paper for an additive supplement:

```bash
python scripts/prepare_redo.py --key <publication-key> --phase 5
```

This restores the archived Phase 1–4 files into `work/<publication-key>/`, overlays the
current accepted final/census state, and creates:

```text
paper.base.final.json
paper.base.census.json
phase5.json
phase5.existing-cards.json
```

Continue with the existing additive Phase 5 authoring/review workflow. On `FINALIZE`,
Phase 5 shows the exact `ADD` / `DELETE` / `MODIFY` set. Additive mode has only `ADD`.
Send `CONFIRM CHANGES` to approve that set; only then does Phase 5 produce the merged
`paper.final.json`. Then use the normal confirm and incorporate commands below.

### Prepare card revision Phase 5

Select the accepted cards that may be modified/deleted, or release all accepted cards:

```bash
python scripts/prepare_redo.py --key <publication-key> --phase 5 --cards 0001,0003,0005
python scripts/prepare_redo.py --key <publication-key> --phase 5 --cards all
```

The selected IDs are a local allowlist; `all` expands to every accepted card in the
publication. Phase 5 may act on any subset, and not every authorised card has to change. Preparation
freezes the accepted baseline and additionally creates:

```text
paper.phase5-targets.json
```

`phase5.json` records the authorised cards and hashes of the accepted baseline and target
objects. Do not edit these preparation files manually.

### Revision Phase 5 — interactive ChatGPT authoring

Start a fresh ChatGPT conversation with:

- `paper.md`
- `metadata.json`
- `paper.census.json`
- `paper.base.final.json`
- `paper.phase5-targets.json`
- `phase5.json`
- `phase5.existing-cards.json`
- `prompts/phase5_prompt.md`

Phase 5 shows the authorised cards and asks what should change. Discuss and refine the
actual modifications/deletions interactively. A modification may change only the card
interpretation, locator, and paired evidence. Card ID, genes, diseases, disease ancestors,
category, evidence tier, and secondary citation remain fixed. A deletion removes the
accepted card, its paired evidence, and its matching audit result. Revision mode does not
add cards; use additive mode for additions.

When ready for independent review, send:

```text
PROVISIONAL
```

Phase 5 writes:

```text
paper.phase5-provisional.json
```

and runs the deterministic validation code embedded in `phase5_prompt.md` before returning
the file. Save the validated provisional locally.

### Revision Phase 5R — non-interactive Claude review

Start a fresh Claude conversation using a different model from Phase 5. Provide exactly:

- `paper.md`
- `paper.phase5-targets.json`
- `paper.phase5-provisional.json`
- `prompts/phase5_review_prompt.md`

Phase 5R is LLM-only: do not interact with or clarify the review. Save its only output as:

```text
paper.phase5-review.json
```

Upload that review to the original Phase 5 ChatGPT conversation. Phase 5 validates that
the review covers the current per-change hashes. If any change fails, discuss and revise
it in Phase 5, issue a new `PROVISIONAL`, and run a fresh Phase 5R review of the current
batch.

### Finalize a revision transaction

When every proposed modification/deletion has a valid passing review, send to the Phase 5
conversation:

```text
FINALIZE
```

Phase 5 shows the exact pending `ADD` / `DELETE` / `MODIFY` set. Revision mode has no
`ADD`. Check it, then send:

```text
CONFIRM CHANGES
```

Only after that explicit confirmation does Phase 5 return a validated transaction asset.
Revision mode does **not** let the LLM write `paper.final.json`:

```text
paper.phase5-revision.json
```

Save it under `work/<publication-key>/`, then apply it locally:

```bash
python scripts/apply_phase5.py --key <publication-key> --cards 0001,0003
```

`--cards` is mandatory and must exactly equal the existing card IDs actually modified or
deleted in the reviewed transaction; do not pass the broader preparation allowlist.
`apply_phase5.py` revalidates that restated change set, the authorised targets, current
accepted baseline, reviewed hashes, and protected fields. It constructs the new
`paper.final.json` from the frozen baseline, applies only the reviewed modifications/
deletions, removes audit results for deleted cards, and recomputes derived coverage fields.

### Confirm and re-incorporate

For either Phase 5 mode, use the normal acceptance command:

```bash
python scripts/confirm.py --key <publication-key>
```

There is no `--phase5` flag. `confirm.py` detects `phase5.json` and applies the matching
additive or revision validation path. Additive supplements are archived under
`archive/<publication-key>/phase5/NNN/`; revisions are archived separately under
`archive/<publication-key>/phase5-revision/NNN/`.

Finally rebuild the corpus:

```bash
python scripts/incorporate.py
```

## Development and prompt maintenance

Developer procedures, prompt regeneration, tests, versioning, and release housekeeping
are documented in [`DEVEL.md`](DEVEL.md).
