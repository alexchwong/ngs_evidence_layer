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

The same PDF bytes always receive the same internal `paper_id`. It is a deterministic
UUID derived from the source SHA-256 and is used only to validate source identity.
Forced reparsing is blocked when that identity exists in `work/`, `accept/`, or
`archive/` unless `--allow-reparse` is supplied.

## 1. Fan out indexed papers

```bash
python scripts/fanout.py --corpus <name>
# or one paper
python scripts/fanout.py --corpus <name> --key <publication-key>
```

The command preflights the complete selected set before writing, allocates stable
publication keys, hashes the Markdown, and creates:

```text
work/<publication-key>/
  paper.md
  metadata.json
```

Existing folders are never changed.

## 2. Phase 1 — census

Start a fresh model session with exactly:

- `work/<publication-key>/paper.md`
- `work/<publication-key>/metadata.json`
- `prompts/phase1_prompt.md`

Save its output as `work/<publication-key>/paper.census.json`. Phase 1 may overwrite that
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

- Any failure: save `paper.review-NNN.json`; no final is written. Every failed-card
  entry includes a precise `reason` and a structured `suggested_action` with one
  repair category plus concise source-bounded detail for Phase 2. The advice is
  non-binding and Phase 2 must verify it against the paper before amending a card.
- All pass: save `paper.final.json`; its `audit.approved_round` identifies the
  exact provisional package audited.

Phase 3 never edits extraction content.

New reviews use these suggested-action categories:

- `narrow_disease_scope`
- `replace_quote`
- `change_category`
- `rewrite_interpretation`
- `split_card`
- `delete_card`
- `add_or_correct_qualifier`
- `correct_escalates_to`

Legacy reviews without `suggested_action` remain valid Phase 2 rework inputs.

## 5. Confirm one paper

```bash
python scripts/confirm.py --key <publication-key>
```

Confirmation checks schemas, IDs, vocabulary, umbrella tags, census reconciliation,
one-to-one card/quote pairing, source-verbatim quotes, complete passing audit,
different model identities, and exact equality with the approved provisional
round. Failure changes nothing.

Success writes:

```text
accept/<publication-key>.final.json
accept/<publication-key>.census.json
```

and moves the complete history from `work/<publication-key>/` to
`archive/<publication-key>/`. Archives are immutable in v0.1.2; reopening is not
provided. The internal `paper_id` remains embedded in metadata, census, provisional,
and final artefacts and must agree across them; users do not use it as a path or CLI
locator.

Manual acceptance is possible only by constructing the same accepted envelope and
setting `acceptance_path` to `manual-or-unverified`. Incorporation cannot recheck
quotes against source Markdown on that path.

## 6. Incorporate all accepted pairs

```bash
python scripts/incorporate.py
```

The command reads `accept/` only. Invalid individual pairs are recorded under
`rejected` and excluded while valid papers build. Accepted filenames are keyed by
`publication_key`, so a mismatched filename and embedded key is rejected. Duplicate
card IDs remain fatal.

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