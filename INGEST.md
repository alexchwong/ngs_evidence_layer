# Ingestion operations — v0.1.2

This is the operator runbook. One publication occupies one independent working
folder; folder contents are its state. Any number of papers may be in flight in
separate fresh model sessions.

## Setup

```bash
python3 -m venv .env
. .env/bin/activate
python -m pip install -r requirements.txt
```

Inputs follow `docs/INPUT.md`. They are private operator data.

## 0. Parse PDFs and resolve citations

Drop PDFs in `pdf/<corpus>/`, then run:

```bash
python scripts/parse_pdfs.py --corpus <name> --mailto <email>
```

Successful sources move to `pdf/archive/<corpus>/`; Markdown and synchronized JSONL
and CSV indexes are written under `input/<corpus>/`. Exit 1 means at least one paper
needs citation repair or failed conversion. Repair citations with the request/apply
or manual-export/manual-apply commands documented in `docs/INPUT.md`.

The same PDF bytes always receive the same ID. Forced reparsing is blocked when that
ID exists in `work/`, `accept/`, or `archive/` unless `--allow-reparse` is supplied.

## 1. Fan out indexed papers

```bash
python scripts/fanout.py --corpus <name>
# or one paper
python scripts/fanout.py --corpus <name> --id <paper-id>
```

The command preflights the complete selected set before writing, allocates stable
publication keys, hashes the Markdown, and creates:

```text
work/<paper-id>/
  paper.md
  metadata.json
```

Existing folders are never changed.

## 2. Phase 1 — census

Start a fresh model session with exactly:

- `work/<paper-id>/paper.md`
- `work/<paper-id>/metadata.json`
- `prompts/phase1_prompt.md`

Save its output as `work/<paper-id>/paper.census.json`. Phase 1 may overwrite that
file when correcting a Phase 2 census critique. Do not start Phase 2 in the same
session.

## 3. Phase 2 — carding or rework

Start a fresh extraction session with:

- `paper.md`, `metadata.json`, `paper.census.json`
- `prompts/phase2_prompt.md`
- the latest `paper.review-NNN.json`, only during rework

If the census is materially deficient, Phase 2 writes the next
`paper.census-critique-NNN.md` and stops. Return that critique to a fresh Phase 1
session.

Otherwise Phase 2 writes a complete package:

```text
paper.provisional-001.json
paper.provisional-002.json   # after review 001
```

The filename round and package `round` must agree. A rework output is a complete
replacement, never a patch.

## 4. Phase 3 — independent audit

Use a different model in a fresh session with exactly:

- `paper.md`
- one `paper.provisional-NNN.json`
- `prompts/phase3_prompt.md`

Do not supply rules, vocabulary, schema, census, or another publication.

- Any failure: save `paper.review-NNN.json`; no final is written.
- All pass: save `paper.final.json`; its `audit.approved_round` identifies the
  exact provisional package audited.

Phase 3 never edits extraction content.

## 5. Confirm one paper

```bash
python scripts/confirm.py --id <paper-id>
```

Confirmation checks schemas, IDs, vocabulary, umbrella tags, census reconciliation,
one-to-one card/quote pairing, source-verbatim quotes, complete passing audit,
different model identities, and exact equality with the approved provisional
round. Failure changes nothing.

Success writes:

```text
accept/<paper-id>.final.json
accept/<paper-id>.census.json
```

and moves the complete history from `work/<paper-id>/` to
`archive/<paper-id>/`. Archives are immutable in v0.1.2; reopening is not provided.

Manual acceptance is possible only by constructing the same accepted envelope and
setting `acceptance_path` to `manual-or-unverified`. Incorporation cannot recheck
quotes against source Markdown on that path.

## 6. Incorporate all accepted pairs

```bash
python scripts/incorporate.py
```

The command reads `accept/` only. Invalid individual pairs are recorded under
`rejected` and excluded while valid papers build. Duplicate publication keys retain
the earliest `accepted_at`, with lexicographic paper ID as a tie-break; losers are
reported and skipped. Duplicate card IDs remain fatal.

Outputs:

```text
output/corpus/nel.corpus.json
output/corpus/nel.index.json
output/reports/build-report.json
```

Quote text is never written to distributable output. Every incorporated paper has
already passed independent audit, so there is no provisional corpus mode.

## Prompt maintenance

Edit prompt prose under `prompts/templates/`, then regenerate one committed prompt:

```bash
python scripts/build_prompts.py --phase 1
python scripts/build_prompts.py --phase 2
python scripts/build_prompts.py --phase 3
```

Read `prompts/meta_prompt.md` before changing extraction rules or schemas.