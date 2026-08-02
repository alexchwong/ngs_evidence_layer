# Ingestion operations

This is the authoritative runbook for publication ingestion. Phases 1–3 are portable: each can run in a repository-backed coding session or in an external chat such as Claude or OpenGPT.

## Non-negotiable contract

- Process exactly one publication in one fresh session.
- Use the repository-local `.env` environment for every command.
- Each model phase receives exactly two files: a copy of the selected paper Markdown and one deterministic `<stem>.phaseN-context.md` file, placed together in the phase outbox.
- Each model phase returns exactly one JSON file.
- Model-authored JSON does **not** complete a phase. Only the deterministic ingestion command may validate, accept, and declare a phase complete.
- Never begin the next phase automatically.
- Phase 3 must use a different model from Phase 2 in a fresh session.
- Never add a fact from model knowledge when the selected paper does not state it.

Set up the environment when needed:

```bash
python3 -m venv .env
. .env/bin/activate
pip install -r requirements.txt
```

Inspect portable state with:

```bash
python scripts/next_paper.py
```

## Directories and artefacts

For each phase, deterministic context, unvalidated responses, archived responses, and accepted outputs are separate:

```text
exchange/ingest/phaseN/outbox/<stem>.md
exchange/ingest/phaseN/outbox/<stem>.phaseN-context.md
exchange/ingest/phaseN/inbox/<stem>.phaseN.json
exchange/ingest/phaseN/archive/<stem>.phaseN.json
output/phaseN/<stem>.phaseN.json
```

The pre-phase command copies the source Markdown into the outbox without changing its content, so the two printed upload paths are in one folder.

The accepted Phase 1 file is a census conforming to `schema/census_schema.json`. Accepted Phase 2 and Phase 3 files conform to the same `schema/ingestion_package_schema.json` contract.

Validation creates temporary private card and quote views in an operating-system
temporary directory, then deletes them. Persistent ingestion state lives only in
`output/phase1/`, `output/phase2/`, and `output/phase3/`; the corpus builder reads
those accepted packages directly. Quote text is validated but never written to
the distributable corpus.

## Standard prepare-or-accept behavior

Every pre-phase command has two modes:

1. If its expected inbox response is absent, it validates prerequisites, selects one paper, and writes one context file.
2. If the expected inbox response exists, it validates the response, atomically promotes it to `output/phaseN/`, archives the submitted response, prints the completion marker, and stops.

A failed response stays in the inbox and is not promoted or archived.

Optional validation-only commands support a local edit/validate loop without accepting the response:

```bash
python scripts/ingest.py validate-phase1 --id <input-id> --response <file>
python scripts/ingest.py validate-phase2 --id <input-id> --response <file>
python scripts/ingest.py validate-phase3 --id <input-id> --response <file>
```

The phase is complete only when the corresponding pre-phase command prints:

```text
PHASE N COMPLETE — VALIDATION PASS
```

An external chat that cannot execute scripts must return JSON only. Its status is `Phase N response authored; deterministic validation pending`, never “complete”.

---

## Phase 1 — census

Prepare the handoff:

```bash
python scripts/ingest.py pre-phase1
```

Upload the printed source Markdown and Phase 1 context file to the model. The context embeds the selected index record, reporting rules, census instructions, census schema, exact filename, validation command, and stop condition.

Save the single JSON response at the printed `exchange/ingest/phase1/inbox/` path. Run the same command again:

```bash
python scripts/ingest.py pre-phase1
```

Validation includes schema, unique census entry IDs, unique genes, and matching source stem. On success the accepted output is:

```text
output/phase1/<stem>.phase1.json
```

**STOP before Phase 2.**

---

## Phase 2 — cards and quotes

Prepare the handoff only after accepted Phase 1 exists:

```bash
python scripts/ingest.py pre-phase2
```

Upload the printed source Markdown and Phase 2 context file. The context embeds all non-paper information needed for carding: rules, disease vocabulary, shared package schema, accepted census, output contract, runnable validation command, and stop condition.

The single response combines publication metadata, cards, and quotes and must include:

```json
{
  "schema_version": "3.0",
  "cards": [],
  "quotes": [],
  "audited": false,
  "audit": null
}
```

Save it at the printed `exchange/ingest/phase2/inbox/` path and rerun:

```bash
python scripts/ingest.py pre-phase2
```

Validation includes the shared schema, vocabulary and umbrella tags, ID discipline, census reconciliation, one-to-one card/quote pairing, quote locators, quote length, and verbatim presence of each quote in the source. Repeated quote text produces a review warning rather than a hard failure because one passage may support distinct roles.

Before submission, Phase 2 must perform the mandatory iterative self-audit in
its generated context. For every card it applies the same two questions as Phase
3: whether the paired quote carries every material assertion, and whether the
card is independently useful rather than materially redundant. A claim being
true elsewhere in the paper is insufficient if its paired quote omits the
threshold, exclusion, hierarchy, marker list, qualifier, nearby sentence, or
table footnote needed to support it. Phase 2 repairs every internal failure and
reruns the audit over the complete package until all cards pass internally, then
repeats deterministic and census reconciliation checks.

This self-audit remains author review, not independent audit. Its internal
verdicts are not returned: the final Phase 2 package still has `audited: false`
and `audit: null`, and Phase 3 remains mandatory.

The accepted output is:

```text
output/phase2/<stem>.phase2.json
```

**STOP before Phase 3.** The accepted Phase 2 package may be incorporated into a provisional corpus as described below.

---

## Phase 3 — independent audit

Prepare the handoff only after accepted Phase 2 exists:

```bash
python scripts/ingest.py pre-phase3
```

Use a different model from Phase 2 in a fresh session. Upload only the printed source Markdown and Phase 3 context file. The context contains the narrow audit instruction and complete accepted Phase 2 package. It deliberately excludes the reporting rules, schemas, census, and other publications.

Return the complete package with extraction content unchanged. The only allowed changes are:

```json
{
  "audited": true,
  "audit": {
    "audit_date": "YYYY-MM-DD",
    "audit_model": "different-model",
    "extraction_model_reviewed": "phase-2-model",
    "results": [
      {"card_id": "...", "verdict": "pass"}
    ]
  }
}
```

Save it at the printed `exchange/ingest/phase3/inbox/` path and rerun:

```bash
python scripts/ingest.py pre-phase3
```

Validation repeats Phase 2 checks, requires an independent audit model, exactly one verdict per card, no failed verdicts, and unchanged extraction content after normalising only `audited` and `audit` back to Phase 2 values. The independent audit judges both quote support and whether each card is independently useful rather than a redundant restatement elsewhere in the package; identical quote text alone is not a failure.

If one or more verdicts are `fail`, the audit itself may still be complete and
well formed, but Phase 3 is not accepted. Do not edit cards in the Phase 3
response and do not flip verdicts to clear the gate. Use the Phase 2 rework path
below.

The accepted output is:

```text
output/phase3/<stem>.phase3.json
```

**STOP before corpus incorporation.**

---

## Phase 2 rework after a failed Phase 3 audit

Phase 3 identifies and explains defects; Phase 2 rework fixes them. The failed
Phase 3 response must remain unchanged in its normal Phase 3 inbox. Prepare a
rework handoff with an explicit input ID:

```bash
python scripts/ingest.py pre-phase2-rework --id <input-id>
```

The command first validates the failed audit as a rework prerequisite: it must
be a complete independent audit of the accepted Phase 2 package, it must not
change extraction content, and it must contain at least one failed verdict. An
accepted Phase 3 package cannot enter rework.

The command writes the source Markdown and a rework context under a numbered
round:

```text
exchange/ingest/phase2/rework/<stem>/round-001/outbox/
```

The context contains the complete Phase 2 instructions, rules, vocabulary,
schema, census, accepted Phase 2 package, and failed Phase 3 audit. The rework
model verifies the failure reasons against the source and returns one complete
corrected Phase 2 package. It may rewrite or requote a card, merge materially
redundant cards, or delete a card with no supported independently useful claim.
It returns `audited: false` and `audit: null`; it does not return a patch or only
the failed cards. The named failures are known defects, not the limit of review:
after repairing them, the model performs the mandatory Phase 2 self-audit over
every card and iterates until the complete package has zero internal failures.

Validate the response at the printed path without accepting it:

```bash
python scripts/ingest.py validate-phase2-rework \
  --id <input-id> \
  --response exchange/ingest/phase2/rework/<stem>/round-001/inbox/<stem>.phase2-rework.json
```

Then rerun the prepare command to accept it:

```bash
python scripts/ingest.py pre-phase2-rework --id <input-id>
```

Acceptance applies all normal Phase 2 validation and preserves publication
identity fields. It archives the superseded Phase 2 package, failed Phase 3
audit, and submitted correction under that round's `archive/` directory before
making the corrected unaudited package the active `output/phase2/` artefact.
Generated Phase 3 handoff and corpus/build outputs derived from the superseded
package are invalidated. Incorporation is never rerun automatically.

Rework is complete only when the command prints:

```text
PHASE 2 REWORK COMPLETE — VALIDATION PASS
```

Then start a fresh Phase 3 session with a different model. Audit the complete
corrected package, not only the previously failed card IDs:

```bash
python scripts/ingest.py pre-phase3 --id <input-id>
```

A later failed audit creates `round-002`, preserving the earlier rework history.

**STOP after preparing or accepting rework. Never begin Phase 3 automatically.**

---

## Corpus incorporation

Corpus incorporation is a separate deterministic operator decision.

### After Phase 2: provisional corpus

```bash
python scripts/ingest.py incorporate --after-phase 2
```

This revalidates accepted Phase 2 packages and writes corpus, index, and build report with:

```json
{"audited": false, "provisional": true}
```

Each incorporated publication source is also marked provisional. Quotes remain excluded from distributable corpus files.

### After Phase 3: audited corpus

```bash
python scripts/ingest.py incorporate --after-phase 3
```

This revalidates accepted Phase 3 packages and writes outputs with:

```json
{"audited": true, "provisional": false}
```

The outputs are:

```text
output/corpus/nel.corpus.json
output/corpus/nel.index.json
output/reports/build-report.json
```

**STOP after incorporation. Do not start retrieval or another ingestion phase.**
