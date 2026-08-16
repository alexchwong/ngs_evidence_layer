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

# Inspect the incorporated corpus as human-readable Markdown.
python scripts/render_corpus.py --list
python scripts/render_corpus.py --key <publication-key> --dest ./temp/corpus
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

Redo/review commands for an accepted paper:

```bash
# Rebuild the census and all downstream phases.
python scripts/prepare_redo.py census --key <publication-key>

# Keep the accepted census and re-extract cards from Phase 2.
python scripts/prepare_redo.py provisional --key <publication-key>

# Review accepted cards interactively in Phase 2R; only explicitly finalized add/modify/delete deltas are applied.
python scripts/prepare_redo.py cards --key <publication-key>

# Complete the remaining normal phases, then confirm without --overwrite.
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
| 1 — census | Fresh ChatGPT or Claude chat | `paper.md`, `metadata.json` | `prompts/phase1_prompt.md` | `paper.census-v001.json` |
| 2 — carding | Fresh chat | `paper.md`, `metadata.json`, active census | `prompts/phase2_prompt.md` | `paper.provisional-v001.json` |
| 3 — independent review | Fresh chat using a **different model from Phase 2** | `paper.md`, active provisional; matching Phase 2R decision ledger when applicable | `prompts/phase3_prompt.md` | matching `paper.review-vNNN.json` |
| 4 — human adjudication | Fresh chat | `paper.md`, `metadata.json`, active census/provisional/review; matching Phase 2R ledger when applicable | `prompts/phase4_prompt.md` | `paper.phase4-decisions[-revRRR]-vNNN.json` plus `paper.final.json`, or a Phase 2R handoff ledger |

### Phase 1 — census

Invoke Phase 1 with full scope or an explicit category-only scope. Phase 1 first
normalizes the requested scope and asks for `CONFIRM`. New ingestions write:

```text
paper.census-v001.json
```

If Phase 2 rejects that census, start a fresh Phase 1 conversation with the original
Phase 1 inputs plus the prior census and its critique. **Do not repeat scope normalization
or ask for `CONFIRM` on a retry.** The prior census carries the already-confirmed scope
(`category_scope` absent means all five categories). Phase 1 reads the complete critique,
repairs the census, then reruns the complete shared census semantic audit rather than
patching only the named defects. The retry writes the next attempt, for example
`paper.census-v002.json`. Never overwrite a failed attempt. Legacy `paper.census.json`
is read as attempt v001; the next retry therefore writes v002.

A prepared accepted-paper census redo restores the accepted census read-only to preserve
the already-confirmed scope and also includes `redo.json`; Phase 1 does not ask for a new
`CONFIRM` and uses `redo.json.next_outputs.census` for the first redo output filename.

Phase 1 now uses four ordered passes: core census drafting; an independent whole-census
semantic audit using the same census gate Phase 2 uses on entry; a model formatting-only
pass; then deterministic structure validation. Any failure returns to census drafting and
all downstream passes are repeated. Known semantic defects cannot be emitted via an
"unresolved" escape.

### Phase 2 — carding and accepted-card review

Normal Phase 2 receives `paper.md`, `metadata.json`, the active census, and
`prompts/phase2_prompt.md`. It first runs the exact Phase 1 deterministic census validator,
then applies the shared census semantic gate. Only after both pass does carding begin.
New ingestion starts with:

```text
paper.provisional-v001.json
```

If Phase 2 rejects the census, it returns `paper.census-critique-vNNN.md`, tied to the
census attempt being criticised. Phase 2 must complete the full shared census semantic
audit first and report all material defects identifiable in that pass, rather than
stopping at the first defect. Redo Phase 1 as above. If Phase 3 rejects the
provisional structurally, rerun Phase 2 with the prior provisional and critique; the
next package uses the next Phase 2 attempt, for example `paper.provisional-v002.json`.
The package `round` advances with Phase 2 attempts. After carding, Phase 2 performs a
separate semantic output audit, then a model formatting-only pass, and finally deterministic
package validation. Failure at any output gate returns to card/evidence generation and the
later gates are repeated; nothing is edited after deterministic validation succeeds.

Accepted-card review uses the **Phase 2R** branch of the Phase 2 prompt. Prepare it with:

```bash
python scripts/prepare_redo.py cards --key <publication-key>
```

The work folder contains `paper.md`, `metadata.json`, the accepted census,
`paper.final.json`, and `redo.json`. The accepted final is an immutable baseline during
discussion. Phase 2R may propose changes, but a proposal is not authorization. Only
explicit user-approved `add`, `modify`, or `delete` decisions are written when the user
sends `FINALIZE`; all other accepted cards/evidence remain exactly unchanged.

Phase 2R has no deterministic input gate. It remains an interactive user-approved delta
workflow; after `FINALIZE`, it constructs only the agreed changes and deterministic delta/
package validation is the final output gate.

The finalized Phase 2R output is a matched pair:

```text
paper.phase2r-decisions-rev001-v001.json
paper.provisional-rev001-v001.json
```

A Phase 2R retry stays in the same revision namespace and increments the attempt. A later
accepted-card review uses the next revision namespace. `prepare_redo.py` records both
matching filenames in `redo.json.next_outputs`. The Phase 2 validator deterministically
checks that the provisional card/evidence diff is exactly the finalized decision ledger.

### Phase 3 — independent review

Use a **different model** from Phase 2. Phase 3 runs no deterministic validation script,
but its review file is the direct input to Phase 4's deterministic entry validator. The
Phase 3 prompt therefore gives the exact review JSON structure and filename convention.
Its workflow is model-formatting input gate → substantive review → model-formatting output
gate. Neither formatting gate performs semantic adjudication, and Phase 3 runs no scripts.
Follow the output contract strictly so Phase 4 can accept it without structural repair.

Give it `paper.md`, the active provisional, and
`prompts/phase3_prompt.md`. If that provisional came from Phase 2R, also give Phase 3 the
matching `paper.phase2r-decisions[-revRRR]-vNNN.json`. Phase 3 preserves any `revNNN`
namespace. Its first review attempt uses at least the provisional attempt number; a Phase
3 retry increments only the review attempt. Examples:

```text
paper.provisional-v002.json       -> paper.review-v002.json
paper.provisional-rev001-v001.json -> paper.review-rev001-v001.json
```

A structurally invalid provisional is returned to Phase 2 as
`paper.provisional-critique[-revNNN]-vNNN.md`. In Phase 2R delta mode, Phase 3
substantively reviews only added/modified cards; unchanged accepted cards carry forward
their prior valid state rather than being reinterpreted under the current prompt.

### Phase 4 — human adjudication

Give Phase 4 `paper.md`, `metadata.json`, the active census, the active provisional, its
matching Phase 3 review, and `prompts/phase4_prompt.md`. Phase 4 first runs deterministic
input validation, then performs interactive adjudication, applies only agreed decisions,
and finishes with deterministic handoff/final validation as the last operation on the
returned files. If the active provisional came
from Phase 2R, also provide its matching Phase 2R decision ledger. The internal `round`
values bind the reviewed package.

Phase 4 directly adjudicates only Phase 3-failed cards. Every direct `retain`, `modify`,
`delete`, or failed-card replacement is recorded with the user's explicit decision in
`paper.phase4-decisions[-revRRR]-vNNN.json`. The validator requires every
provisional→final card/evidence difference to match that ledger exactly.

If the user wants to change a Phase 3-passed card or add an unrelated card, Phase 4 must
not refuse and must not finalize first. On user `PHASE2R`, it returns a Phase 4 handoff
decision ledger. Phase 2R then uses the current Phase 4 state as its immutable baseline,
applies only subsequently approved deltas, and sends added/modified cards through Phase
3 again before returning to Phase 4.

Legacy archives using `paper.census.json`, `paper.provisional-001.json`, and
`paper.review-001.json` remain valid and require no migration. Existing package filenames
remain unchanged; new decision-ledger files follow the same optional `revRRR` plus `vNNN`
namespace as their associated provisional/review.

## 5. Confirm the paper

After Phase 4 is complete:

```bash
python scripts/confirm.py --key <publication-key>
```

`confirm.py` is the deterministic acceptance gate. If validation fails, nothing is
accepted. For new schema-5.1 workflows it rechecks both Phase 2R and Phase 4 decision
ledgers against the archived/current baselines, so an unapproved card/evidence change
cannot be accepted merely because an earlier model step emitted it.

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
cards/<publication-key>.md
evidence/<publication-key>.md
```

`incorporate.py` reads from `accept/`. Invalid accepted packages are reported and
excluded; valid accepted papers are incorporated. `nel.index.json` exposes paper
acceptance-version history. `cards/` is the committed human-readable card view;
`evidence/` is the local evidence-and-interpretation view and remains ignored. Each
incorporation replaces the generated Markdown views so they remain synchronized with
the accepted corpus.

### Render the incorporated corpus for inspection

`scripts/render_corpus.py` provides a read-only Markdown view of the committed corpus
outputs. List every publication key, card count, acceptance version, and citation:

```bash
python scripts/render_corpus.py --list
```

Render one publication and all of its accepted cards:

```bash
python scripts/render_corpus.py --key <publication-key>
```

Both commands print Markdown to standard output by default. To write files instead, pass
a destination directory:

```bash
python scripts/render_corpus.py --list --dest ./temp/corpus
python scripts/render_corpus.py --key <publication-key> --dest ./temp/corpus
```

List mode writes `./temp/corpus/index.md`; publication mode writes
`./temp/corpus/<publication-key>.md`. Publication output includes each card's full ID,
short numeric ID, category, genes, diseases, disease ancestors, evidence tier,
interpretation, locator, and secondary citation. 
By default, the renderer reads:

```text
output/corpus/nel.index.json
output/corpus/nel.corpus.json
```

To inspect a completed but not yet accepted `paper.final.json` directly from the working
folder, use `--from-work`:

```bash
python scripts/render_corpus.py --key <publication-key> --from-work
```

This reads `work/<publication-key>/paper.final.json` and
`work/<publication-key>/metadata.json`. Because the package has not yet been accepted,
the rendered acceptance version is `—`.

To inspect the current accepted package directly, without requiring incorporation, use
`--from-accept`:

```bash
python scripts/render_corpus.py --key <publication-key> --from-accept
```

This reads `accept/<publication-key>.final.json`, including the embedded metadata and
final package. For a legacy Phase 5 supplement/revision or a current redo, it reports the acceptance
version from the newest dated modification record. Otherwise it reports `latest_version`
for an overwritten paper, falling back to the original `accepted_in_version`.

`--from-work` and `--from-accept` are mutually exclusive, require `--key`, and cannot be
used with `--list`. Both support `--dest` in the same way as default publication mode.

Use `--index <path>` and `--corpus <path>` to inspect alternate generated files. `--list`
only requires the index; `--key` requires both files. The renderer does not modify the
corpus, index, or accepted ingestion state.

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

## 6A. Redo or review an accepted paper

`prepare_redo.py` restores only the source and intermediate files required to resume the
requested model phase. In `cards` mode, authorization is recorded later by the interactive
Phase 2R decision ledger; preparation itself does not authorize a card edit. Baseline
hashes in `redo.json` are used to detect stale accepted state at confirmation.

### Redo the census

```bash
python scripts/prepare_redo.py census --key <publication-key>
```

Restores `paper.md` and `metadata.json`. `redo.json` names the next census, provisional,
and review attempt so regenerated files cannot collide with archived legacy or versioned
filenames. Complete Phases 1–4 and confirm normally.

### Redo the provisional extraction

```bash
python scripts/prepare_redo.py provisional --key <publication-key>
```

Restores `paper.md`, `metadata.json`, and the accepted census using its archived filename.
The census is read-only; if it must change, use `census` mode. Complete Phases 2–4.

### Review accepted cards

```bash
python scripts/prepare_redo.py cards --key <publication-key>
```

Restores `paper.md`, `metadata.json`, the accepted census, and `paper.final.json` from the
archive/accepted state into `work/`. Phase 2R is interactive: the accepted final is the
immutable baseline, proposed changes do nothing until explicitly approved by the user,
and `FINALIZE` writes both the decision ledger and the revised provisional. Deterministic
validation rejects any card/evidence difference not represented by an approved
`add`/`modify`/`delete` decision. Phase 3 reviews the changed/new subset and Phase 4 then
uses the normal adjudication workflow. There is no separate Phase 5 or Phase 5R.

### Confirmation and history

After completing the remaining phases:

```bash
python scripts/confirm.py --key <publication-key>
python scripts/incorporate.py
```

Confirmation verifies the accepted baseline has not changed since preparation, validates
the complete new lineage, and deterministically rechecks the Phase 2R/Phase 4 authorized
deltas before replacing the current accepted/archive state. It snapshots the superseded
archive under `archive/<publication-key>/redo/NNN/`. Historical accepted packages and
archived folders created by the former Phase 5 workflow remain readable; new workflows
do not create Phase-5 artefacts.

### Filename compatibility

Legacy names are permanent read aliases for first attempts:

| Legacy | Interpreted as |
|---|---|
| `paper.census.json` | census v001 |
| `paper.provisional-001.json` | provisional v001 |
| `paper.review-001.json` | review v001 |

Do not rename old archives. New retries inspect both legacy and versioned names when
choosing the next attempt, so a legacy `paper.provisional-001.json` is followed by
`paper.provisional-v002.json`, not another v001.

Decision ledgers are additive workflow-control files and do not rename package artefacts:

```text
paper.phase2r-decisions-vNNN.json
paper.phase2r-decisions-revRRR-vNNN.json
paper.phase4-decisions-vNNN.json
paper.phase4-decisions-revRRR-vNNN.json
```

Their namespace matches the provisional/review episode they authorize.

## Development and prompt maintenance

Developer procedures, prompt regeneration, tests, versioning, and release housekeeping
are documented in [`DEVEL.md`](DEVEL.md).
