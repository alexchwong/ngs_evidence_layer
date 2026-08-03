# Input corpus contract — v0.1.2

PDFs and generated input state are private and ignored by git:

```text
pdf/<corpus>/                     pending operator PDF queue
pdf/archive/<corpus>/             successfully processed sources
input/<corpus>/
  markdown/<stem>--<id8>.md        archived evidence source
  index/papers.jsonl              canonical index
  index/papers.csv                regenerated read-only view
  citations/                      DOI and manual repair files
```

Run `scripts/parse_pdfs.py --corpus <name>` to convert pending PDFs with locked
OpenDataLoader settings. Identity is UUIDv5 over the PDF SHA-256, so identical PDF
bytes always receive the same paper ID. Conversion publishes Markdown atomically;
no structured JSON or images are retained.

## Index contract

`papers.jsonl` contains one object per source checksum. Records include identity,
relative Markdown path, source filename and hash, status, citation and provenance,
canonical `publication_key`, and parse diagnostics. Status is one of:

- `ingested`: Markdown exists and citation authors, title, and year are resolved;
- `citation-pending`: Markdown exists but citation repair is required;
- `failed`: conversion failed and will be retried on the next parse run.

`citation_source` is `crossref-doi`, `model-supplied-doi`, or `operator`.
`papers.csv` is regenerated after every index update and is never an input.

Parse-time publication-key collisions warn but retain both records. Fan-out
recomputes the key, rejects stored-key mismatches, and aborts if the selected corpus
contains duplicate publication keys.

## Citation resolution

The parser detects a DOI only in front and back matter and uses Crossref only when
`--mailto` or `NEL_CROSSREF_MAILTO` is supplied. It performs no fuzzy title search.
Citation failure does not roll back valid Markdown.

Repair pending records with:

```bash
python scripts/citations.py request --corpus <name>
python scripts/citations.py apply --corpus <name> --response response.json
python scripts/citations.py manual-export --corpus <name>
python scripts/citations.py manual-apply --corpus <name> --csv worksheet.csv
```

The model path accepts DOI candidates only, re-resolves them through Crossref, and
checks title overlap. The manual path accepts a batch-atomic CSV; authors are
semicolon-separated and DOI may be empty. Derived displays and publication keys are
always rebuilt by code.

## Evidence boundary and reparsing

PDF conversion and Crossref DOI lookup are input-layer operations. After conversion,
Markdown is the only archived evidence source: model phases, confirmation, cards,
and citations never read or cite a PDF.

`--force` reparsing is blocked if the content-addressed paper already exists in
`work/`, `accept/`, or `archive/`. `--allow-reparse` explicitly overrides this
safeguard. A parser upgrade can change Markdown and invalidate verified quotes, so
schema or rule changes require re-ingestion rather than mechanical migration.