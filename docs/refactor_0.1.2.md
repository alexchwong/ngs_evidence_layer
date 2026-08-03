# ngs_evidence_layer 0.1.2 — PDF ingestion layer

Build specification. Decisions I made myself, rather than ones you specified, are
marked **[D]** and carry a one-line rationale so you can overturn them cheaply.

---

## 1. Scope

0.1.2 adds a deterministic PDF-to-Markdown front end, moves `publication_type`
from fan-out to the model phases, and changes duplicate-publication handling at
incorporation from a fatal build abort to a per-paper skip.

What is unchanged: the phase model, folder-as-state, quote discipline, retrieval
and rendering, and the rule that Markdown is the archived evidence source.

Three constraints from 0.1.1 are relaxed or restated:

| 0.1.1 | 0.1.2 |
|---|---|
| No network DOI lookup | Crossref lookup permitted, for the input layer only |
| No model-derived bibliography | Permitted for DOI recovery, recorded as such |
| PDF conversion is outside this project | Conversion is in scope; extraction from PDF is still never the evidence path |

The evidence path is still Markdown only. Nothing in this layer reads a PDF after
conversion, and no card may cite one.

---

## 2. Directory layout

```text
pdf/<corpus>/                     gitignored. Operator drops PDFs here.
pdf/archive/<corpus>/             gitignored. Sources moved here on success.
input/<corpus>/                   gitignored. Unchanged 0.1.1 contract.
  markdown/<stem>--<id8>.md
  index/papers.jsonl              canonical
  index/papers.csv                synchronised view, read-only for operators
  citations/request-<UTC>.md      generated repair prompt
  citations/response.json         operator-supplied model DOI return
  citations/manual-<UTC>.csv      generated no-DOI citation worksheet
work/, accept/, archive/          unchanged
output/                           unchanged
```

`.gitignore` gains `/pdf/`.

**[D] `pdf/archive/<corpus>/` rather than `pdf/<corpus>/archive/`.** Keeps the
drop folder containing exactly the work not yet done, so `ls pdf/<corpus>` is the
pending queue. Archived PDFs are never deleted by any command in this repository.

`input/<corpus>/json/` and `input/<corpus>/related/` do not exist. Structured JSON
and images are not written.

---

## 3. Paper identity

```python
PAPER_NAMESPACE = uuid.UUID("6f1c2a34-8d5b-4e77-9a03-5c7e2b8f1d94")  # fixed constant

def paper_uuid(sha256_hex: str) -> str:
    return str(uuid.uuid5(PAPER_NAMESPACE, sha256_hex))

stem = f"{safe_stem(source.stem)}--{paper_id[:8]}"
```

Identity is content-addressed: the same PDF always yields the same `paper_id`,
across corpora and across re-parses. `uuid5` satisfies the `format: uuid`
constraint in `metadata_schema.json`, which is enforced — `package_validation`
constructs its validator with a `FormatChecker()`.

**[D] The namespace UUID is a hard-coded module constant, not configuration.**
Making it configurable would let two operators produce different IDs for the same
paper, which is the failure this design exists to prevent.

Consequences, stated plainly: a different scan of the same publication is a
different `paper_id`. That case is caught by publication-key collision, not by
checksum, and is the reason for the warnings in §7.

---

## 4. `scripts/parse_pdfs.py`

Ported from `pdf_parsing`, reduced to what NEL consumes.

```bash
python scripts/parse_pdfs.py --corpus <name> [paths ...]
                             [--dry-run] [--force] [--allow-reparse]
                             [--keep-source] [--quiet]
                             [--mailto <email>]
```

Behaviour per PDF:

1. Compute SHA-256; derive `paper_id` and `stem`.
2. Skip if the index already holds that checksum with a non-`failed` status,
   unless `--force`.
3. Convert to Markdown into a temporary directory, then publish atomically to
   `input/<corpus>/markdown/<stem>.md`.
4. Extract a DOI from the Markdown; resolve the citation (§6).
5. Write the index record; move the PDF to `pdf/archive/<corpus>/` unless
   `--keep-source`.

Failures are recorded with `status: "failed"` and a diagnostic, and are retried on
the next run without `--force`.

### Locked conversion settings

Conversion parameters are not exposed as flags, so a given PDF always produces the
same Markdown and therefore the same `markdown_sha256`.

```python
opendataloader_pdf.convert(
    input_path=[...],
    output_dir=str(work_output),
    format="markdown",        # JSON dropped
    reading_order="xycut",    # geometric segmentation; the multi-column default
    keep_line_breaks=False,   # reflow paragraphs into single logical lines
    use_struct_tree=False,    # ignore embedded tags
    image_output="off",       # no figure extraction
    quiet=args.quiet,
)
```

**[D] `use_struct_tree=False`.** Tagged-PDF structure trees in journal output are
frequently wrong about table boundaries, and their quality varies by publisher, so
enabling them makes output quality depend on an invisible property of the source
file. Geometric analysis is worse on average for headings and better where it
matters here — cell boundaries in dense tables.

**[D] `keep_line_breaks=False`.** `confirm.py` verifies quotes verbatim against
`paper.md`. `validation.normalise()` collapses whitespace, so reflow is safe, and
hard-wrapped lines make a model far likelier to truncate a quote at a line end.

**[D] `reading_order="xycut"`.** Two-column layouts are the common case for the
publications this corpus ingests; naive stream order interleaves the columns.

Add to `requirements.txt`:

```text
# OpenDataLoader PDF requires Python 3.10+ and Java 11+.
opendataloader-pdf>=2,<3
```

**[D] Crossref is called through `urllib.request` from the standard library.** One
GET against one endpoint does not justify adding `requests` to a dependency list
that currently holds `jsonschema` and `referencing` only.

### Table integrity check

After conversion, count Markdown table delimiter rows and flag any table whose
row cell counts are inconsistent with its header. This does not fail the paper; it
writes `parse.table_warnings` into the index record and prints a warning.

**[D] Malformed tables warn rather than fail.** `docs/INPUT.md` already places the
judgement of whether a table is intact with the reader at Phase 1, and a paper
whose sole broken table is irrelevant to myeloid genes is still worth carding.

---

## 5. Index record — `input/<corpus>/index/papers.jsonl`

One object per source checksum. Field order fixed for stable diffs.

```json
{
  "id": "5e2b1c77-3a44-5f10-9b6d-0c81ef42a7d5",
  "markdown_path": "markdown/who5--5e2b1c77.md",
  "source_filename": "who5.pdf",
  "sha256": "…64 hex…",
  "status": "ingested",
  "citation": {
    "authors": ["Khoury JD", "Solary E"],
    "title": "The 5th edition of the World Health Organization classification…",
    "journal": "Leukemia",
    "year": 2022,
    "volume": "36",
    "issue": "7",
    "pages": "1703-1719",
    "doi": "10.1038/s41375-022-01613-1"
  },
  "citation_source": "crossref-doi",
  "citation_resolved_at": "2026-08-03T04:11:07+00:00",
  "publication_key": "khoury-2022-the-5th-edition-of-the-world-health",
  "parse": {
    "parser": "opendataloader-pdf",
    "parser_version": "2.1.0",
    "parsed_at": "2026-08-03T04:10:55+00:00",
    "markdown_sha256": "…64 hex…",
    "archived_pdf": "pdf/archive/myeloid-core/who5.pdf",
    "doi_detected": "10.1038/s41375-022-01613-1",
    "table_warnings": [],
    "error": ""
  }
}
```

`publication_type` is **absent** — it is now a Phase 1 judgement (§8).

`status` is one of:

| Status | Meaning | Fan-out |
|---|---|---|
| `ingested` | Markdown published, citation resolved and complete | Eligible |
| `citation-pending` | Markdown published, citation unresolved or incomplete | Rejected |
| `failed` | Conversion failed; no Markdown | Rejected |

`citation_source` is one of `crossref-doi`, `model-supplied-doi`, `operator`.

**[D] `publication_key` is computed at parse time and stored in the index.** It is
derived by `make_key.py` from the citation the parser just resolved, so storing it
costs nothing and lets both the parser and fan-out warn about collisions before a
model session is spent. Fan-out still recomputes it and treats its own value as
authoritative; a mismatch is a fan-out error.

**[D] Status flips to `ingested` automatically when a citation resolves.** You
ruled that model-supplied citations are not blocked pending operator sign-off, and
a Crossref-verified citation is stronger evidence than that, so a gate here would
only slow the machine path.

`papers.csv` is regenerated atomically alongside the JSONL after every run, with
columns: `id`, `status`, `source_filename`, `markdown_path`, `citation_source`,
`doi`, `year`, `first_author`, `title`, `publication_key`, `error`. It is a view;
hand-edits to it are ignored and overwritten.

Operator citation repair does not require hand-editing `papers.jsonl`. The manual
CSV workflow in §6 exports a dedicated worksheet and applies it through validated,
atomic code. `papers.csv` remains a read-only synchronised view and is never an
input.

**[D] Manual citation authors use a semicolon-separated cell.** For example,
`Khoury JD; Solary E`. The export file is written and read with Python's `csv`
module, so commas and quotes in titles and journal names retain standard CSV
escaping while the author-array encoding remains explicit and reversible.

---

## 6. Citation resolution

### Automatic path

1. Regex the published Markdown for a DOI, using the existing Crossref-recommended
   pattern. **[D] Search only the first 4000 characters plus the last 2000.** A
   whole-document scan reliably finds a DOI belonging to a cited reference rather
   than to the paper; front matter and back matter are where the paper's own DOI
   lives.
2. `GET https://api.crossref.org/works/<doi>` with a `User-Agent` carrying
   `mailto:` from `--mailto` or `NEL_CROSSREF_MAILTO`. **[D] No mail address means
   no lookup, not an anonymous request.** Crossref's polite pool is a courtesy
   condition, and being rate-limited mid-corpus is worse than being told up front.
3. Map `author` → `"Family I"` initials form, `title[0]`, `container-title[0]`,
   `issued.date-parts[0][0]`, `volume`, `issue`, `page`.
4. Require authors, title and year. Anything short of that is `citation-pending`,
   regardless of what else Crossref returned.

**[D] There is no title-based Crossref query.** A fuzzy title search returns a
plausible wrong paper often enough that its errors would be invisible — the wrong
citation on the right Markdown is the one failure this pipeline cannot detect
downstream.

Network failure, a 404, or an incomplete record all yield `citation-pending` with
the reason in `parse.error`. Conversion is never rolled back for a citation
failure; the Markdown is already good.

### Repair paths — `scripts/citations.py`

```bash
python scripts/citations.py request --corpus <name>   # writes the prompt
python scripts/citations.py apply   --corpus <name> --response <file>
python scripts/citations.py manual-export --corpus <name> [--output <file>]
python scripts/citations.py manual-apply  --corpus <name> --csv <file>
```

**[D] All four subcommands live in one script.** They share index access and
record-matching logic, and splitting them invites the repair paths to disagree
about identity or write semantics.

`request` emits one Markdown file covering every `citation-pending` paper in the
corpus, at `input/<corpus>/citations/request-<UTC>.md`. Per paper it supplies the
`paper_id`, the extracted title candidate, the first 1200 characters of body text
after the title as an abstract proxy, and any DOI already detected. **[D] Title
candidate is the first ATX heading in the Markdown, falling back to the first
non-empty line.** Cheap, deterministic, and wrong in a way the human reading the
model's return will notice.

The prompt instructs the model to search for each paper and return **the DOI
only**, keyed by `paper_id`, as a JSON array; it states explicitly that a DOI it
cannot verify against the paper's title must be returned as an empty string rather
than guessed.

```json
[
  {"paper_id": "5e2b1c77-…", "title_seen": "…", "doi": "10.1038/s41375-022-01613-1"},
  {"paper_id": "9a04df31-…", "title_seen": "…", "doi": ""}
]
```

`apply` reads that file and, for each row:

- matches on `paper_id`; an unknown or already-`ingested` id is reported and
  skipped;
- **[D] re-resolves the returned DOI against Crossref rather than trusting the
  model's bibliography.** You permitted model-derived citations, but the model
  only needs to supply the identifier — letting the script fetch the record keeps
  every citation string in the corpus machine-derived and byte-identical to the
  automatic path;
- **[D] verifies the Crossref title against `title_seen` by normalised token
  overlap, rejecting the row below 0.6 Jaccard similarity.** The one failure mode
  of DOI recovery is a confidently wrong identifier, and this catches it without
  needing an exact string match;
- on success writes the citation with `citation_source: "model-supplied-doi"` and
  flips status to `ingested`;
- on any failure leaves the citation blank and the status `citation-pending`.

A partial return, an unrecognised key, and a contradicted DOI are all per-row
outcomes. The file is never rejected wholesale. `apply` prints a per-row table and
exits non-zero if any row failed.

**[D] A returned DOI that contradicts `parse.doi_detected` is applied, with a
warning.** The extracted DOI is the weaker signal — it is regex output from a
document that may cite a hundred others.

#### Manual citation path — no DOI

`manual-export` writes a timestamped CSV at
`input/<corpus>/citations/manual-<UTC>.csv` unless `--output` is supplied. It emits
every `citation-pending` paper exactly once with these columns:

```text
paper_id,authors,title,journal,year,volume,issue,pages,doi
```

Only `paper_id` is populated. All citation cells are empty for the operator to
complete; `doi` may remain empty. Export does not modify either index file.

`manual-apply` validates the complete CSV before changing the master index:

- each `paper_id` is unique, known, and currently `citation-pending`;
- `authors` is a non-empty semicolon-separated list whose members remain non-empty
  after trimming;
- `title` is non-empty and `year` is an integer accepted by the metadata schema;
- `journal`, `volume`, `issue`, `pages`, and `doi` may be empty;
- display citation and `publication_key` are rebuilt through `make_key.py`; no
  operator-supplied derived value is accepted.

If any row is invalid, nothing is written. If all rows are valid, the command sets
the citation, `status: "ingested"`, `citation_source: "operator"`,
`citation_resolved_at` to the application time, and the canonical
`publication_key`, then atomically rewrites `papers.jsonl` once and regenerates
`papers.csv` from the same in-memory records.

**[D] Manual application is batch-atomic, unlike model DOI application.** The CSV
is an operator-authored structured update to the canonical index; refusing a
partially valid worksheet makes correction and rerun safe and prevents the JSONL
and CSV views from representing different batches.

---

## 7. Duplicate detection

Three points, escalating:

| Point | Condition | Action |
|---|---|---|
| Parse | Same `sha256` already indexed | Silent skip, or reprocess under `--force` |
| Parse | Same `publication_key`, different `sha256` | Warning; record still written |
| Fan-out | Same `publication_key` within the selected corpus | Abort, as in 0.1.1 |
| Incorporate | Same `publication_key` across `accept/` | Skip the loser, warn, build the rest |

The parse-time warning names both `paper_id`s and both source filenames. It is the
expected signal for a second scan, a preprint alongside its published version, or
the same guideline supplied twice with different filenames.

**[D] Parse-time collision does not block the write.** The operator may genuinely
want both files present while deciding which to keep, and the fan-out abort is
already an unavoidable gate before any model work.

---

## 8. `publication_type` moves to the phases

It leaves `metadata.json` entirely.

| Artefact | Change |
|---|---|
| index record | Field removed |
| `metadata.json` | `publication_type` removed; `citation_source` added |
| `paper.census.json` | `publication_type` added, required, closed enum |
| `paper.provisional-NNN.json` | `publication_type` added, required; copied verbatim from the census |
| `paper.final.json` | Inherits it as a package superset; authoritative at incorporation |

- **Phase 1** assigns it and records a one-line justification in
  `publication_type_basis`. **[D] The justification is required.** It costs one
  line and is what makes a Phase 3 disagreement adjudicable rather than a coin
  toss between two model opinions.
- **Phase 2** copies both fields verbatim. It may revise them only when acting on
  a `paper.review-NNN.json` that names the type as a defect.
- **Phase 3** audits the type against the paper as a package-level verdict
  alongside its per-card verdicts. A disagreement is a review failure, returning
  the package to Phase 2 by the existing route.
- **`confirm.py`** checks that census and final agree on `publication_type`,
  alongside its existing census reconciliation.
- **`incorporate.py`** reads `package["publication_type"]` instead of
  `metadata["publication_type"]` for the corpus document and the
  `by_publication_type` postings.

The enum is unchanged: `guideline`, `consensus statement`, `primary study`,
`systematic review`, `narrative review`, `other`.

**[D] Phase 3 receives no additional context to make this judgement.** Its
deliberate starvation is load-bearing; publication type is legible from the
paper's own front matter and structure.

---

## 9. Schema changes

| Schema | Version | Change |
|---|---|---|
| `metadata_schema.json` | `1.0` → `1.1` | Remove `publication_type`; add `citation_source` (enum) and `citation_resolved_at` (date-time, nullable) |
| `census_schema.json` | `3.0` → `3.1` | Add required `publication_type`, `publication_type_basis` |
| `ingestion_package_schema.json` | `4.0` → `4.1` | Add required `publication_type`, `publication_type_basis`; audit block gains `publication_type_verdict` |
| `accepted_package_schema.json` | `1.0` → `1.1` | Add required `accepted_at` (date-time) and `accepted_at_source` (`confirm`, `file-mtime`) |
| `disease_vocabulary.json` | — | Unchanged |

All four keep `additionalProperties: false` and pin `schema_version` with `const`,
so every artefact currently in `work/`, `accept/` and `archive/` becomes invalid.

**[D] No dual-version acceptance. `package_validation` recognises 0.1.2 versions
only, and papers in flight are re-ingested.** This is the project's existing
position — a schema change changes the meaning of what a phase was asked to
produce, and `publication_type` in particular was never a judgement any prior
paper's model was asked to make, so a mechanical migration would fabricate an
audit that did not happen.

Both fixtures under `tests/fixtures/work/` are regenerated by hand.

**[D] `accepted_at` is added because `acceptance_path` is an enum, not a
timestamp.** The tiebreak in §10 needs an ordering and there is currently none.
`confirm.py` writes it at acceptance with `accepted_at_source: "confirm"`.

For a manual package dropped directly into `accept/` without `accepted_at`,
`incorporate.py` takes the final file's mtime, converts it to an ISO-8601 UTC value,
adds `accepted_at_source: "file-mtime"`, and atomically rewrites the accepted
package before schema validation or duplicate selection. It then reloads the
persisted envelope. This is performed only while `accepted_at` is absent; every
later build uses the stored value and never consults mtime again.

**[D] Failure to persist a synthesized timestamp rejects that paper.** Using an
mtime only in memory could produce a duplicate winner that changes on the next
build. Persist-before-use makes the first normalization the only machine-dependent
event. A clone, copy, or restore can affect an as-yet unnormalised manual drop, but
cannot change the winner after one successful normalization.

---

## 10. `incorporate.py` — duplicate publication keys

Present behaviour: a repeated `publication_key` or `card_id` raises before
anything is written, so one duplicate stops the corpus.

New behaviour:

- Before loading accepted pairs, normalize each manual `*.final.json` lacking
  `accepted_at` by persisting its file mtime and `accepted_at_source:
  "file-mtime"`. Already timestamped packages are never rewritten for this purpose.
- **Duplicate `publication_key`** — retain the earliest `accepted_at`; ties broken
  by lexicographic `paper_id`. Losers are recorded in `index["rejected"]` and the
  build report with `duplicate publication_key <key>: superseded by <paper_id>`,
  excluded from the corpus, and the build continues. A warning is printed.
- **Duplicate `card_id`** — **[D] remains a fatal build failure.** A repeated card
  ID between two papers means key derivation is broken, not that two publications
  are the same; continuing would emit a corpus whose index cannot address its own
  cards.

**[D] The rejection is one-sided, not mutual.** Both-reject is defensible but
loses audited work over an operator filing error, and the retained paper is
deterministic and named in the report, so the outcome is reproducible and
reviewable.

---

## 11. `fanout.py` changes

Minimal. Paths are unchanged, because `input/<corpus>/` keeps its 0.1.1 shape.

- `load_index` no longer requires `publication_type`; it does require
  `citation_source`.
- It rejects any record whose `status` is not `ingested` with the reason given —
  `citation-pending` reports the paper as awaiting citation repair.
- It rejects any record whose citation lacks authors, title or year, even at
  status `ingested`. **[D] This check is duplicated rather than trusted from the
  parser**, because `papers.jsonl` is hand-editable and fan-out is the gate that
  precedes irreversible model spend.
- `metadata_for` stops writing `publication_type` and starts writing
  `citation_source`.
- If the record carries a `publication_key`, fan-out compares it to its own
  computed value and errors on a mismatch, which detects a citation edited after
  parse without a re-run.

---

## 12. Exit codes

| Code | `parse_pdfs.py` | `citations.py apply` |
|---|---|---|
| 0 | All PDFs converted and all citations resolved | Every row applied |
| 1 | Converted, but at least one paper is `citation-pending` or failed | At least one row rejected |
| 2 | Usage, environment or index error; nothing written | Response file unreadable or malformed |

**[D] `citation-pending` is exit 1, not 0.** It is the state that requires the
operator to do something next, and a zero exit is how it would be missed.

---

## 13. Tests

New, in `tests/test_parse.py`:

- `paper_uuid` is stable and produces valid UUIDs; stem ends `--<id8>`.
- Index round-trip: JSONL and CSV stay consistent; hand-edited CSV is overwritten.
- Crossref mapping from a stored fixture response, with no network in the test
  suite. **[D] The Crossref client takes an injectable fetch function**, defaulting
  to `urllib`, so the suite never touches the network.
- Incomplete Crossref record yields `citation-pending`.
- `citations.py apply`: good row, unknown id, blank DOI, title-mismatch rejection,
  contradicted-DOI warning.
- `citations.py manual-export`: pending-only selection, empty citation cells, stable
  columns, and CSV escaping.
- `citations.py manual-apply`: no-DOI success, multi-author round trip, canonical
  key/display derivation, and batch-atomic rejection for unknown, duplicate,
  already-ingested, blank-required, or malformed-year rows.
- Table-integrity flagging on a malformed fixture.

Amended:

- `test_ingest.py` — fixtures carry `citation_source`, drop `publication_type`;
  new cases for fan-out rejection at `citation-pending` and at an empty citation.
- `test_pipeline.py` — duplicate `publication_key` produces a skip with the
  earliest `accepted_at` retained, not an abort; duplicate `card_id` still aborts.
  A manual package's missing timestamp is synthesized from mtime and persisted;
  changing mtime after that first build does not alter the stored timestamp or the
  duplicate winner. Equal timestamps are resolved by lexicographic `paper_id`.

Conversion itself is not tested. It needs a JVM and a real PDF; the seam is
`convert_batch()`, stubbed in tests.

---

## 14. Migration order

One file at a time, per `.clinerules`.

1. `schema/*.json` — version bumps and field moves.
2. `scripts/package_validation.py` — pin new versions; add census/final
   `publication_type` agreement.
3. `scripts/index_store.py` — new, corpus-parameterised.
4. `scripts/parse_pdfs.py` — new.
5. `scripts/citations.py` — new; DOI/model repair and manual CSV export/apply.
6. `scripts/fanout.py` — index contract and `metadata_for`.
7. `scripts/confirm.py` — `accepted_at`, `accepted_at_source`, type agreement.
8. `scripts/incorporate.py` — one-time persisted mtime normalization,
   duplicate-key skip; type from package.
9. `prompts/templates/phase1|2|3` and `build_prompts.py` — `publication_type`
   assignment, propagation, audit.
10. `docs/INPUT.md` rewrite; `README.md` boundaries; `INGEST.md` step 0;
    `.gitignore` `/pdf/`; `requirements.txt`; `NEWS.md`.
11. Regenerate fixtures; rewrite tests.

`docs/INPUT.md` needs its closing paragraph replaced: PDF conversion is now in
scope, Crossref lookup is used, model-derived DOI recovery is permitted and
recorded, and the re-ingestion rule stands unchanged.

---

## 15. Open items I did not decide

- Whether `--force` reparse should be blocked when the `paper_id` already has a
  folder under `work/`, `accept/` or `archive/`. Re-parsing changes
  `markdown_sha256` and invalidates quotes `confirm.py` already verified, so I
  have left `--allow-reparse` in the CLI as a placeholder without specifying which
  directories it consults.
- Whether a corpus should be re-parseable in bulk after an OpenDataLoader upgrade,
  and how the resulting Markdown drift is reconciled against accepted papers.
- Whether `citation_source` should influence anything downstream of provenance —
  a retrieval filter, or a rendered marker on a model-recovered citation.
- Whether Crossref's `type` field is worth storing as a hint for the Phase 1
  `publication_type` judgement, or whether that would anchor the model.
