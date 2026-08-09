# Ingesting publications

This is the operator guide for adding papers to the NEL corpus.

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
`accept/`, `archive/`, and `curation/`. Do not commit these directories' contents.

## Setup

From the repository root:

```bash
python3 -m venv .env
. .env/bin/activate
python -m pip install -r requirements.txt
```

## Move private corpus state between computers

`scripts/transport.py` packages the ignored private ingestion directories:
`pdf/`, `input/`, `work/`, `accept/`, `archive/`, and `curation/`. Reproducible
committed `output/` artefacts are not included.

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

Existing work folders are not modified.

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

## 7. Phase 5 — add evidence missed during the original ingest

Use Phase 5 when an already accepted paper supports an additional interpretation that
was missed during Phases 1–4.

Phase 5 is **additive only**. It cannot modify or delete existing accepted cards or
change the census. If the missing interpretation requires census expansion, perform a
full re-ingest instead.

### Prepare the accepted paper

Restore the archived paper and ingestion history into a new work folder:

```bash
python scripts/prepare_phase5.py --key <publication-key>
```

This copies the archived Phase 1–4 files back into:

```text
work/<publication-key>/
```

and overlays the current accepted final/census state. It also creates:

```text
paper.base.final.json
paper.base.census.json
phase5.json
phase5.existing-cards.json
```

The original archive remains in place.

### Phase 5 authoring

Start a fresh ChatGPT or Claude conversation with:

- `paper.md`
- `metadata.json`
- `paper.census.json`
- `paper.base.final.json`
- `phase5.json`
- `phase5.existing-cards.json`
- `prompts/phase5_prompt.md`

The model first asks which interpretation or interpretations you believe the paper
supports but the accepted cards missed.

For each requested interpretation, it checks for existing equivalent cards, rereads the
paper for support, and discusses any proposed new cards with you.

When the additions are ready for independent review, save:

```text
paper.phase5-provisional.json
```

### Independent Phase 5 review

Start a fresh conversation using a **different model** from the Phase 5 authoring model.

Provide exactly:

- `paper.md`
- `paper.phase5-provisional.json`
- `prompts/phase5_review_prompt.md`

Save:

```text
paper.phase5-review.json
```

Every proposed card must pass. If a reviewed card is changed, regenerate the provisional
file and repeat the independent review.

### Finalize the supplement

Return to the Phase 5 authoring/finalization conversation and provide the completed
`paper.phase5-review.json`.

When satisfied, send:

```text
FINALIZE
```

The model writes a merged:

```text
paper.final.json
```

containing the unchanged accepted cards plus the independently reviewed new cards.

### Confirm and re-incorporate

Confirm Phase 5 with the normal command:

```bash
python scripts/confirm.py --key <publication-key>
```

There is **no `--phase5` flag**. `confirm.py` detects `phase5.json` and applies the Phase
5 validation path automatically.

On success it updates the accepted package and archives the completed supplement under:

```text
archive/<publication-key>/phase5/NNN/
```

Finally rebuild the corpus:

```bash
python scripts/incorporate.py
```

## Development and prompt maintenance

Developer procedures, prompt regeneration, tests, versioning, and release housekeeping
are documented in [`DEVEL.md`](DEVEL.md).
