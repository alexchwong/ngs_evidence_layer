# Output directories

`INGEST.md` is the authoritative ingestion runbook. This file only explains the
roles of the output folders.

## Accepted phase artefacts

```text
phase1/<stem>.phase1.json   accepted census
phase2/<stem>.phase2.json   accepted cards-and-quotes package, not audited
phase3/<stem>.phase3.json   accepted independently audited package
```

These are the stable interfaces between ingestion phases. A file appears here
only after `scripts/ingest.py` has validated and accepted the corresponding inbox
response. Models and operators must not write these files directly.

The accepted packages are also the direct inputs to corpus incorporation. Phase
2 and Phase 3 packages contain private quotes, which are validated against the
source Markdown but omitted from every distributable corpus file. Temporary card
and quote views used by the existing validator are deleted after each command.

## Incorporated outputs

```text
corpus/nel.corpus.json
corpus/nel.index.json
reports/build-report.json
```

These are written only by the explicit `incorporate` job. Incorporation after
Phase 2 produces a provisional corpus; incorporation after Phase 3 produces an
audited, non-provisional corpus.
