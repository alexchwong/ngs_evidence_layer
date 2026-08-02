# ngs_evidence_layer

A corpus-grounded evidence layer for myeloid NGS interpretation. It converts one
publication at a time into gene-indexed evidence cards backed by separately held
verbatim quotes, then retrieves a deterministic, citable evidence block for a
case.

It is **not a report writer**. It collates what publications state; it does not
reconcile classifiers, rank findings, make clinical decisions, or draft a final
interpretative report.

## Setup

Use the repository-local virtual environment:

```bash
python3 -m venv .env
. .env/bin/activate
python -m pip install -r requirements.txt
python scripts/vocab.py
python -m unittest discover -s tests -v
```

Publication inputs are archived Markdown plus an index. See `input/README.md` for
that input contract. PDF extraction is outside this project, and only intact
Markdown tables are interpreted.

## Ingestion

`INGEST.md` is the authoritative operator and agent runbook. It defines strict
read/write allowlists, preconditions, outputs, validation, external audit handoff,
and stop conditions.

Ingestion has three explicitly bounded model phases. Each `pre-phaseN` command
either prepares the two-file model handoff when no response is present, or
validates and accepts the response already placed in that phase's inbox. It never
starts the next phase.

```bash
# Inspect which publication and phase are next.
python scripts/next_paper.py

# Prepare or accept the census response, then stop.
python scripts/ingest.py pre-phase1

# After accepted Phase 1 exists, prepare or accept cards and quotes, then stop.
python scripts/ingest.py pre-phase2

# In a fresh session with a different model, prepare or accept the audit, then stop.
python scripts/ingest.py pre-phase3
```

Each phase uses `exchange/ingest/phaseN/`: `outbox/` holds the source copy and
deterministic context, `inbox/` receives one unvalidated JSON response, and
`archive/` receives that response only after validation passes. Stable accepted
responses are written to `output/phaseN/`. Validation uses temporary private
card and quote views; the corpus builder reads accepted phase packages directly,
so no second persistent set of per-publication files is maintained.

Phase 3 is deliberately performed in a fresh session by a different model from
Phase 2. The Phase 3 context contains the accepted Phase 2 package and narrow
audit instruction; the auditor returns the complete package with only audit
metadata added.

Failed Phase 3 verdicts intentionally block acceptance. Phase 3 reports defects
but never edits extraction content. Return a valid failed audit to a separate
Phase 2 rework round with:

```bash
python scripts/ingest.py pre-phase2-rework --id <input-id>
```

The rework handoff includes the source, accepted Phase 2 package, and failure
reasons. A corrected complete Phase 2 package replaces the active package only
after deterministic validation; the superseded package and failed audit remain
archived. The corrected package then requires a fresh full Phase 3 audit. See
`INGEST.md` for validation-only commands and rework paths.

Corpus incorporation is a separate operator decision:

```bash
# Build a provisional corpus from accepted Phase 2 packages.
python scripts/ingest.py incorporate --after-phase 2

# Or build an audited corpus from accepted Phase 3 packages.
python scripts/ingest.py incorporate --after-phase 3
```

The core ingestion guarantees are:

- one publication per model session;
- the census is the completeness contract;
- every card has exactly one source-verbatim quote;
- the audit model must differ from the extraction model;
- every card must pass audit before entering the audited corpus;
- a corpus incorporated after Phase 2 is explicitly marked provisional;
- quote text never enters the distributable corpus; and
- each job stops at its declared phase boundary.

For extraction and audit semantics, see `SKILL.md`. For the closed reporting
rules, see `rules/agreed_reporting_rules.md`.

## Retrieval

Retrieval is deterministic after the bounded model step that extracts a provisional
disease and genes from the case.

```bash
# Diagnosis cards and closed-set escalation candidates.
python scripts/retrieve.py diagnosis \
    --genes NPM1 SRSF2 DNMT3A \
    --provisional-disease MDS \
    --corpus output/corpus/nel.corpus.json \
    --index output/corpus/nel.index.json \
    --output step2.json

# After selecting refined_disease only from the allowed escalation result.
python scripts/retrieve.py full \
    --diagnosis-result step2.json \
    --refined-disease AML \
    --driven-by <card-id> \
    --output bundle.json

python scripts/render.py --bundle bundle.json --output block.md
```

`block.md` is the evidence-layer deliverable. It is passed to a separate
report-writing step where clinical synthesis, negative-fact filtering, and final
judgement occur.

Retrieval rejects a stale index whose hash does not match the corpus. Genes the
corpus cannot address are named as unassessed rather than answered from model
memory.

## Evidence and vocabulary boundaries

The disease vocabulary is closed and categorical. Specific diseases require their
configured umbrella tags so broad retrieval cannot silently miss them. Changing
the vocabulary changes the meaning of existing omissions and therefore requires
re-ingestion and re-audit, not a mechanical field migration.

Different publications coexist even when they disagree. Duplicate claims across
publications are allowed; only byte-identical rendered interpretations collapse,
while retaining all citations.

The corpus is the sole evidence source at retrieval time. The project does not use
live databases, model approval status or jurisdiction, infer missing literature,
or promote an unsupported statement from model knowledge.
