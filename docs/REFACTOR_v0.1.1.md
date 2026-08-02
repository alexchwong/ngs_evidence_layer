# ngs_evidence_layer — refactor build specification

Decisions I made myself, rather than ones you specified, are marked **[D]**. Each
carries a one-line rationale so you can overturn it cheaply.

---

## 1. Principles this refactor rests on

1. **Prompts are data, not code.** Everything an LLM needs to work a phase lives
   in a paper-agnostic Markdown file under `prompts/`. Paper-specific data lives
   only in JSON.
2. **Folder contents are the state machine.** There is no phase counter, no
   queue, no selection script. A working folder's phase is whatever its files
   imply.
3. **Papers are independent.** Any number can be in flight at once, in parallel
   chat sessions, with no shared mutable state.
4. **Non-deterministic checks belong to the phase that runs them.** Exit
   validation is the terminal instruction of a phase; entry validation is the
   first instruction. Both are performed by the model working that phase.
5. **Deterministic checks are few and structural.** Three points only: fan-out,
   confirm, incorporate.
6. **Only the corpus ships.** Everything upstream is gitignored.

---

## 2. Directory layout

```text
prompts/                          committed, paper-agnostic
  meta_prompt.md
  phase1_prompt.md
  phase2_prompt.md
  phase3_prompt.md
rules/agreed_reporting_rules.md   committed
schema/*.json                     committed
scripts/                          committed
output/corpus/                    committed artefact (nel.corpus.json, nel.index.json)
output/reports/build-report.json  committed artefact

input/                            gitignored, operator-managed
  <corpus>/markdown/<stem>--<id8>.md
  <corpus>/index/papers.jsonl
work/<paper-id>/                  gitignored
archive/<paper-id>/               gitignored
accept/                           gitignored, flat
```

**[D] `work/`, `archive/` and `accept/` are new top-level directories rather than
subdirectories of `output/`.** `output/` currently mixes shipped artefacts with
pipeline scratch, which is why it needs three README files to explain itself.
Separating them makes the `.gitignore` two lines instead of a pattern list.

**[D] `exchange/` is deleted outright.** Its inbox/outbox/archive triplet existed
to separate unvalidated from accepted responses. With validation moved into the
model session, the distinction no longer has a mechanical meaning.

---

## 3. Working folder contents

```text
work/<paper-id>/
  paper.md                        working copy of the source
  metadata.json                   written once at fan-out, never edited
  paper.census.json               phase 1 output
  paper.census-critique-001.md    phase 2 entry rejection of the census
  paper.provisional-001.json      phase 2 output, round 1
  paper.review-001.json           phase 3 rejection of round 1
  paper.provisional-002.json      phase 2 output, round 2
  paper.final.json                phase 3 approval, unnumbered
```

Round numbers appear in the filename **and** in the file's own metadata, so a
file separated from its folder is still identifiable.

`paper.final.json` is deliberately unnumbered: there is exactly one, and it is
the only artefact that leaves the working folder. Its metadata records which
provisional round it approved.

**[D] The census is unnumbered and rewritten in place if phase 1 is rerun.** A
census rejected at phase 2 entry has no downstream dependants to invalidate, so
versioning it buys nothing. Critique files are numbered so repeated rejections
are visible.

---

## 4. `metadata.json`

Written once by fan-out. Models read it; nothing writes to it afterwards.

```json
{
  "paper_id": "3f0a91c2-7b4e-4c11-9d02-8a5f6e1c0d33",
  "corpus": "myeloid-core",
  "stem": "who5--3f0a91c2",
  "publication_key": "khoury-2022-who-classification",
  "citation": { "authors": [], "title": "", "journal": "", "year": 2022,
                "volume": "", "issue": "", "pages": "", "doi": "" },
  "citation_incomplete": ["issue"],
  "publication_type": "guideline",
  "source_filename": "who5.pdf",
  "source_sha256": "...",
  "markdown_sha256": "...",
  "created_at": "2026-08-02T00:00:00Z"
}
```

`publication_key` is allocated at fan-out by the existing `make_key.py` logic,
so card IDs are stable from the first session and cross-paper key collisions are
detected before any model work is done.

**[D] `citation` and `publication_type` move from the phase 2 model to fan-out.**
They are bibliographic facts available from the index and reference metadata, not
extraction judgements. Removing them from the phase 2 output shrinks what the
audit has to hold constant.

---

## 5. `prompts/` — contents and contract

Each `phaseN_prompt.md` is uploaded by the operator alongside the paper's files
and must be complete: an LLM with only that prompt plus the phase's inputs can
work the phase. Each contains, in order:

1. Role and scope — what this phase does and, explicitly, what it must not do.
2. Inputs it will have been given, by filename.
3. Entry validation instruction (phase 2 and 3 only).
4. The working method.
5. Output contract — filename, exact JSON shape, embedded schema.
6. Exit validation instruction and the iterate-until-clean rule.
7. Stop condition — what "done" means and what it must not claim.

**[D] The reporting rules, disease vocabulary and JSON schemas are inlined into
each prompt at build time by `scripts/build_prompts.py`, from
`rules/agreed_reporting_rules.md`, `schema/disease_vocabulary.json` and the
relevant schema files.** Hand-maintained copies inside four prompt files will
drift from `disease_vocabulary.json`, and drift there is exactly the failure the
existing `check_vocabulary_consistency()` was written to catch. Generation keeps
one source of truth while still yielding a single self-contained file to upload.
The generated prompts are committed so the operator never has to run a build step
before uploading. If you would rather hand-write them, delete `build_prompts.py`
and add the vocabulary consistency check to the test suite instead.

`meta_prompt.md` is addressed to whoever maintains this repository, not to a
phase model. It states:

- which prompt sections are generated and must be edited at source;
- which are hand-written prose and may be edited directly;
- that a change to the reporting rules, vocabulary or schemas requires
  regenerating prompts, then **re-ingesting affected publications** — a rule that
  changes what gets extracted changes the meaning of existing omissions, and a
  mechanical field migration cannot recover a card that was never written;
- that phase 3's prompt must never gain the reporting rules, schemas or census,
  because an auditor holding them starts improving cards;
- the invariants any edit must preserve: one quote per card, gene-indexed cards,
  closed vocabulary with umbrella tagging, no model knowledge in output.

---

## 6. Phase contracts

### Phase 1 — census

| | |
|---|---|
| Session | Fresh. Model A. |
| Inputs | `paper.md`, `metadata.json`, `phase1_prompt.md` |
| Output | `paper.census.json` |
| Entry validation | None |
| Exit validation | Self, iterative, until clean |

Unchanged in substance from the current build: one full sequential pass
including tables and footnotes; per-gene claim locations and category coverage;
`geneless_statements`; `supplement_flags`; no refusal.

Exit validation asks: is every section and table accounted for; does every entry
carry a locator; are gene symbols valid HGNC; are entry IDs and genes unique;
does anything in the paper that the reporting rules cover appear nowhere in the
census. The model repairs and re-runs until clean, and must not report completion
before it does.

**[D] Cap exit-validation passes at 3.** Same ceiling as the phase 2 self-audit,
for the same reason: an unbounded loop either converges early or is not going to.
On reaching the cap without a clean pass, the model reports completion with an
explicit `validation_unresolved` list in the census, which phase 2's entry check
will see.

### Phase 2 — carding

| | |
|---|---|
| Session | Fresh. Model A or B — must differ from phase 3. |
| Inputs | `paper.md`, `paper.census.json`, `phase2_prompt.md`, optionally `paper.review-NNN.json` |
| Output | `paper.provisional-NNN.json` |
| Entry validation | Census; review file if present |
| Exit validation | Self-audit, capped at 3 passes |

**Entry.** Validate the census against the paper. If it is materially deficient,
stop, author `paper.census-critique-NNN.md` naming the specific gaps, and do not
proceed. The operator uploads that critique into a fresh phase 1 session.

If `paper.review-NNN.json` is present, validate it too: it must reference card
IDs that exist in the corresponding provisional package, and each failure must
carry a reason. A malformed review is reported and the session stops.

**Working method.** As the current build. Rework is not a mode — it is this
phase run again with one extra input. The named failures are known defects, not
the limit of review; the model returns a complete corrected package, not a patch.

**Exit.** The mandatory self-audit survives, capped at 3 passes. Both questions
per card (quote support, independent utility), diagnosis cards additionally
checked for `escalates_to` fidelity, repair and re-run over the whole package.
Internal verdicts are not returned. If cards remain failing at the cap, the model
narrows or deletes them rather than submitting them.

**[D] The exit self-audit and the exit validation prompt are the same thing.**
You asked to keep the self-audit and I saw no second check worth adding beside
it; two overlapping exit passes would be cost without independence.

### Phase 3 — audit

| | |
|---|---|
| Session | Fresh. Model B — must differ from phases 1 and 2. |
| Inputs | `paper.md`, `paper.provisional-NNN.json`, `phase3_prompt.md` |
| Output | `paper.final.json` on full pass, `paper.review-NNN.json` on any failure |
| Entry validation | Provisional package well-formedness |
| Exit validation | Every card has exactly one verdict |

Deliberately starved of context: no reporting rules, no schemas, no census, no
other publication. Audit only — it never authors, rewrites, extends, re-scopes or
proposes cards.

Two questions per card, plus `escalates_to` fidelity on diagnosis cards, exactly
as currently specified.

- **All pass** → write `paper.final.json`: the provisional package with audit
  metadata attached (`audit_date`, `audit_model`, `extraction_model_reviewed`,
  `approved_round`, one verdict per card).
- **Any fail** → write `paper.review-NNN.json` only. Do not write a final. Do not
  flip a verdict to clear the gate. Each failure names the unsupported assertion
  or the material redundancy.

**[D] `paper.final.json` is a superset of the provisional package, not a new
shape.** One less schema to maintain, and it makes "extraction content unchanged"
a diff rather than a translation.

**[D] Model identity is self-declared in each artefact's metadata and checked
deterministically at confirm.** Nothing in the pipeline can verify which model a
chat session actually used; recording it and rejecting a match at confirm is the
same guarantee the current build offers, moved to the last gate.

---

## 7. Validation matrix

| Point | Kind | Runs where | On failure |
|---|---|---|---|
| Fan-out | Deterministic | `scripts/fanout.py` | Abort; no folder created |
| Phase 1 exit | LLM, self | Phase 1 session | Iterate ≤3, then flag |
| Phase 2 entry — census | LLM | Phase 2 session | Stop; emit critique Markdown |
| Phase 2 entry — review | LLM | Phase 2 session | Stop; report to operator |
| Phase 2 exit | LLM, self-audit | Phase 2 session | Iterate ≤3, then narrow or delete |
| Phase 3 entry | LLM | Phase 3 session | Stop; report to operator |
| Phase 3 exit | LLM | Phase 3 session | Emit review, no final |
| Confirm | Deterministic | `scripts/confirm.py` | Reject; nothing moves |
| Incorporate | Deterministic | `scripts/incorporate.py` | Warn, skip paper, build the rest |

---

## 8. Scripts

Four scripts survive or are new. `next_paper.py` and `ingest.py` are deleted.

### `scripts/fanout.py --corpus <name> [--id <paper-id>]`

Reads `input/<corpus>/index/papers.jsonl`. For each record, validates the index
contract (unique id, `status: ingested`, filename ends `--<id8>`), allocates
`publication_key`, hashes the Markdown, and creates `work/<paper-id>/` with
`paper.md` and `metadata.json`.

Idempotent: an existing folder is left alone and reported. Aborts on duplicate
`publication_key` across the corpus before any folder is written.

**[D] It does not copy the phase 1 prompt into the working folder.** The prompt
is generic and lives in `prompts/`; copying it per paper creates N stale copies
the moment the rules change. The operator uploads `prompts/phase1_prompt.md`
directly.

### `scripts/build_prompts.py`

Regenerates `prompts/phase*.md` from rules, vocabulary and schemas. Run after any
change to those sources. Fails if the vocabulary and the card schema enum
disagree — the existing `check_vocabulary_consistency()`, relocated.

### `scripts/confirm.py --id <paper-id>`

Deterministically validates `work/<paper-id>/paper.final.json`:

- schema; ID discipline; `card_id` prefixed with the metadata's `publication_key`
- closed vocabulary and umbrella tagging
- one-to-one card/quote pairing; quote length; locators
- **every quote present verbatim in `paper.md`** — the last point at which this is
  possible with certainty
- census reconciliation
- audit block: one verdict per card, none failing, audit model differs from
  extraction model

On pass: copies `paper.final.json` and `paper.census.json` into flat `accept/` as
`<paper-id>.final.json` and `<paper-id>.census.json`, then moves
`work/<paper-id>/` to `archive/<paper-id>/` intact. On failure: nothing moves; a
report is printed.

**[D] Accept filenames key on `paper_id`, not stem.** Stems are human-friendly but
only the id is guaranteed unique by the input contract, and a flat folder is where
a collision would silently overwrite.

The manual path — the operator dropping both files into `accept/` by hand —
bypasses this and is validated at incorporation instead.

### `scripts/incorporate.py`

Reads `accept/` only. For each paired final + census:

- revalidates schema, IDs, vocabulary, umbrella tags, census reconciliation, and
  the audit block
- **cannot** re-check quotes verbatim, since `paper.md` is not here
- on failure: prints a warning, records the paper in the build report as
  `rejected` with reasons, and **excludes it from the corpus without aborting**
- strips all quote text
- builds `nel.corpus.json`, `nel.index.json`, `output/reports/build-report.json`

The index keeps its current postings (gene, disease, category, `escalates_to`,
tier, year, publication type), per-paper entries, corpus SHA-256, counts and
extraction ratio. It gains a `rejected` block.

The `provisional`/`audited` flags are removed: every corpus is audited by
construction.

---

## 9. What is deleted

- `scripts/next_paper.py`; `scripts/ingest.py` in full
- `pre-phase1/2/3`, `pre-phase2-rework`, `validate-phase1/2/3`,
  `validate-phase2-rework`, `incorporate --after-phase`
- the `exchange/` tree; `output/phase1|2|3/`; rework round directories
- generated per-paper `<stem>.phaseN-context.md` files
- audit instructions embedded in Python (`audit_instruction()`,
  `portable_audit_instruction()`)
- temporary card/quote build views (`package_as_build_views`,
  `package_as_validation_views`) — the package is read directly
- the provisional corpus path, `--allow-unaudited`, and both flags
- `--after-phase`, `--allow-incomplete` (incorporation now always builds what it
  can and reports the rest)
- the skip-report path

**[D] The skip report is deleted.** It marked a publication that could not be
carded at all. Under folder-as-state, an abandoned paper is a working folder that
never reaches `accept/`, which is the same information with no second mechanism.
If you want it back, it belongs as a `metadata.json` field written by hand.

**[D] `schema/card_schema.json` and `schema/quote_schema.json` are merged into
`ingestion_package_schema.json`.** They only ever described the temporary build
views, which no longer exist. `card_schema.json`'s disease enum moves to the
package schema and stays under the consistency check.

---

## 10. Migration order

1. Extract the phase prompts out of `SKILL.md` and `ingest.py` into `prompts/`;
   add `meta_prompt.md`; write `build_prompts.py`.
2. Reduce `SKILL.md` to orientation, design rationale and scope exclusions.
   Rewrite `INGEST.md` as a short operator runbook of folders and transitions.
3. Merge the schemas; relocate the vocabulary consistency check.
4. Write `fanout.py`; delete `next_paper.py`.
5. Split `ingest.py`: validation logic into a shared module, acceptance into
   `confirm.py`, build into `incorporate.py`. Delete the rest.
6. Update `.gitignore`: `input/`, `work/`, `archive/`, `accept/`.
7. Rewrite the test suite against the new file contracts; the two synthetic
   fixtures survive as pre-built working folders.

---

## 11. Open items I did not decide

- Whether a paper in `archive/` can be reopened, and by what mechanism.
- Whether `accept/` files should be signed or hashed against their archive
  counterparts to detect hand-editing of the manual path.
- Whether corpus versioning and sealing — currently deferred — should land in the
  same refactor, since `incorporate.py` is being rewritten anyway.
