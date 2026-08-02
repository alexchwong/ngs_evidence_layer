# Input corpus contract

Input is private, operator-managed data and is ignored by git:

```text
input/<corpus>/
  markdown/<stem>--<first-8-characters-of-paper-id>.md
  index/papers.jsonl
```

`papers.jsonl` contains one JSON object per line:

```json
{
  "id": "3f0a91c2-7b4e-4c11-9d02-8a5f6e1c0d33",
  "markdown_path": "markdown/who5--3f0a91c2.md",
  "source_filename": "who5.pdf",
  "sha256": "optional 64-character source-file SHA-256",
  "status": "ingested",
  "publication_type": "guideline",
  "citation": {
    "authors": ["Khoury JD"],
    "title": "The 5th edition of the World Health Organization classification",
    "journal": "Leukemia",
    "year": 2022,
    "volume": "36",
    "issue": "7",
    "pages": "1703-1719",
    "doi": "10.1038/s41375-022-01613-1"
  }
}
```

## Required invariants

- `id` is a unique UUID.
- `markdown_path` is unique and relative to `input/<corpus>/`.
- `status` is exactly `ingested`.
- the Markdown filename ends `--<id8>.md`.
- the Markdown exists before fan-out.
- `source_filename`, `publication_type`, and complete primary citation authors,
  title, and year are supplied by the operator.
- publication type is one of: `guideline`, `consensus statement`, `primary study`,
  `systematic review`, `narrative review`, `other`.
- absent citation strings are represented as empty strings, not invented values.

Fan-out derives `publication_key` and display citation deterministically using
`scripts/make_key.py`, computes the Markdown hash, and rejects duplicate publication
keys across the selected corpus before creating any working folder. No network DOI
lookup or model-derived bibliography is used.

Markdown is the archived evidence source. PDF conversion is outside this project,
and only intact Markdown tables may be interpreted. Re-ingestion requires the exact
Markdown that was originally carded; a schema or reporting-rule change cannot be
recovered by mechanically migrating fields.