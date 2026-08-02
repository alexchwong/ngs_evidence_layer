# Input corpora

Create one folder per corpus:

```
input/<corpus>/markdown/<stem>--<first 8 chars of id>.md
input/<corpus>/index/papers.jsonl
```

One JSON object per line in `papers.jsonl`:

```json
{"id": "3f0a91c2-7b4e-4c11-9d02-8a5f6e1c0d33", "markdown_path": "markdown/who5--3f0a91c2.md", "source_filename": "who5.pdf", "sha256": "...", "doi": "10.1038/s41375-022-01613-1", "status": "ingested"}
```

`id` and `markdown_path` are required and must be unique; `status` must be
`ingested`; the Markdown filename must end with `--` plus the first eight
characters of the id. `scripts/next_paper.py` and `scripts/build_corpus.py` both
refuse an index that breaks any of these, because a drifted filename silently
pairs a card file with the wrong source.

Extracted Markdown is archived here rather than treated as scratch. On a schema
change, re-ingestion re-audits every card from a publication against its archived
source and modifies, adds or deletes cards as required. It is not a mechanical
field migration, and it cannot be done at all if the Markdown that was actually
carded has been thrown away.

Markdown only. This tool does not touch PDFs, and only intact Markdown tables are
interpreted — a table that lost its structure during extraction should be
reported in the census, not guessed at.
