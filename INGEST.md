# Ingestion operations — v0.1.3

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

## Transport private state between computers

The ignored pre-corpus directories can be exported as one compressed, verified
archive. The bundle includes `pdf/`, `input/`, `work/`, `accept/`, and `archive/`;
committed and reproducible `output/` artefacts are not included.

On the source computer:

```bash
python scripts/transport.py export --output nel-private-state.tar.gz
```

Transfer that file using an appropriate private channel. Gzip compression does not
encrypt the source publications, evidence fragments, or workflow state, so protect
the bundle as private data. On the destination computer, from the repository root:

```bash
# Inspect the result without writing anything.
python scripts/transport.py import nel-private-state.tar.gz --dry-run

# Import after the dry run succeeds.
python scripts/transport.py import nel-private-state.tar.gz
```

Every archived file is recorded in a versioned manifest with its size and SHA-256.
Import rejects malformed paths, unsupported entries, and files that fail verification.
It adds missing files and skips byte-identical files. If any destination path already
contains different content, the complete import is refused without overwriting or
partially merging the bundle. Export likewise refuses to overwrite an existing bundle;
choose a new output filename for each snapshot.

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

## 3. Phase 2 — carding

Start a fresh extraction session with:

- `paper.md`, `metadata.json`, `paper.census.json`
- `prompts/phase2_prompt.md`

If the census is materially deficient, Phase 2 writes the next
`paper.census-critique-NNN.md` and stops. Return that critique to a fresh Phase 1
session.

Otherwise Phase 2 writes a complete package:

```text
paper.provisional-001.json
```

The filename round and package `round` are always 001/1. Phase 2 is not repeated
after audit.

For each card, `diseases` records only source-grounded exact clinical applicability.
`disease_ancestors` records the canonical direct and transitive parents derived from
the `umbrella` graph in `schema/disease_vocabulary.json`, excluding exact values.
Ancestors support broad corpus indexing but never widen case retrieval;
`diseases_covered` is therefore the unique union of exact `diseases` only.

## 4. Phase 3 — independent audit

Use a different model in a fresh session with exactly:

- `paper.md`
- `paper.provisional-001.json`
- `prompts/phase3_prompt.md`

Do not supply rules, vocabulary, schema, census, or another publication.

- Always save `paper.review-001.json`; Phase 3 never writes a final.
- The review contains one pass/fail result for every card. Passed cards contain only
  their ID and verdict. Failed cards additionally include the failure type, precise
  reason, defensibility statement, and structured suggested action.
- A quote failure must restate the quote read by Phase 3 in its review details.

Phase 3 never edits extraction content and is not repeated.

For every typed evidence bundle, Phase 3 must independently verify that contextual
fragments structurally govern the claim, table relations reconstruct all applicable
headers and qualifiers, and provenance metadata does not assign meaning absent from
the verbatim fragments.

Publication type uses the six-value semantic taxonomy defined in
`schema/publication_type_vocabulary.json`. Publisher labels such as “special report”
are not additional values. Phase 3 passes any package value defensible under the
taxonomy and requests a change only when that value clearly fails its definition
and exactly one other allowed value is better supported. This ambiguity rule keeps
fresh audit sessions from alternating between equally plausible labels.

Failed-card reviews use these suggested-action categories:

- `narrow_disease_scope`
- `replace_evidence`
- `change_category`
- `rewrite_interpretation`
- `split_card`
- `delete_card`
- `add_or_correct_qualifier`

Validate the complete review against its provisional package:

```bash
python scripts/validate_review.py \
  --review work/<publication-key>/paper.review-001.json \
  --provisional work/<publication-key>/paper.provisional-001.json
```

The validator checks `schema/review_schema.json` plus cross-artefact identity,
round, model, complete card coverage and ordering, counts, card IDs, conditional
failure details, and publication-type invariants.

## 5. Phase 4 — human adjudication and finalization

Start a fresh finalization session with:

- `paper.md`, `metadata.json`, `paper.census.json`
- `paper.provisional-001.json`, `paper.review-001.json`
- `prompts/phase4_prompt.md`

Phase 4 presents every card to the human, including Phase 3-passed cards. The human
chooses the final action for each card. Phase 4 applies source-supported decisions
and writes `paper.final.json`; it never creates another provisional package or sends
cards back to Phase 3. All resulting cards receive passing entries in the existing
final audit shape because the human review and action taken are final.

## 6. Confirm one paper

```bash
python scripts/confirm.py --key <publication-key>
```

Confirmation checks schemas, IDs, vocabulary, canonical disease ancestors, census reconciliation,
one-to-one card/evidence-bundle pairing, independently source-verbatim fragments,
bundle references and role constraints, complete Phase 3 review, complete passing
final audit, different model identities, and lineage to the approved provisional
round. Phase 4's adjudicated extraction content may differ from the provisional.
Failure changes nothing.

Success writes:

```text
accept/<publication-key>.final.json
accept/<publication-key>.census.json
```

and moves the complete history from `work/<publication-key>/` to
`archive/<publication-key>/`. Archives are immutable in v0.1.3; reopening is not
provided. The internal `paper_id` remains embedded in metadata, census, provisional,
and final artefacts and must agree across them; users do not use it as a path or CLI
locator.

Manual acceptance is possible only by constructing the same accepted envelope and
setting `acceptance_path` to `manual-or-unverified`. Incorporation cannot recheck
evidence fragments against source Markdown on that path.

## 7. Incorporate all accepted pairs

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

Evidence bundles and fragment text are never written to distributable output. Every
incorporated paper has completed independent Phase 3 audit and human Phase 4
adjudication, so there is no provisional corpus mode.

## Prompt maintenance

Edit prompt prose under `prompts/templates/`, then regenerate one committed prompt:

```bash
python scripts/build_prompts.py --phase 1
python scripts/build_prompts.py --phase 2
python scripts/build_prompts.py --phase 3
python scripts/build_prompts.py --phase 4
```

Read `prompts/meta_prompt.md` before changing extraction rules or schemas.