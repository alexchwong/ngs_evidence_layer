# NEWS

## 0.1.3

- Replaced the single contiguous quote contract with one typed evidence bundle per
  card: `contiguous_text`, `composite_text`, or `table_relation`.
- Added independently verbatim, locatable evidence fragments, atomic `support_map`
  references, and explicit table links between cells, headers, legends, and footnotes.
- Added deterministic bundle cardinality, reference, role, source-presence, and
  aggregate-length validation while keeping private evidence out of public artefacts.
- Made scope governance, complete table reconstruction, and prevention of evidence
  laundering mandatory Phase 3 audit checks.
- Bumped ingestion packages to schema version 5.0; version 4.2 packages and external
  consumers of the former `quotes` array require re-ingestion or adaptation.

## 0.1.2

- Added deterministic, content-addressed PDF-to-Markdown ingestion with locked
  OpenDataLoader settings and atomic publication.
- Added DOI detection, Crossref resolution, model-assisted DOI recovery, and a
  batch-atomic manual citation worksheet.
- Made JSONL the canonical input index and added a synchronized read-only CSV view.
- Made the human-readable publication key the operator-facing work-folder identity
  and card-ID prefix while retaining the content-derived paper UUID internally.
- Moved publication-type assignment and justification into Phase 1, propagation into
  Phase 2, and independent audit into Phase 3.
- Hardened all model phases with exclusive output contracts and mandatory pre-output
  gates; strengthened Phase 2 qualifier, quote, and independent-utility checks, and
  added bounded Phase 3 reviewer suggestions for rejected packages.
- Added stable acceptance timestamps and changed duplicate publication keys at
  incorporation from fatal errors to deterministic per-paper rejection.
- Replaced escalation-candidate selection with evidence-bounded diagnostic
  adjudication over structured case facts and all gene-matched diagnosis cards.
  Adjudication now separates a source-supported diagnostic label from the major
  disease category used for deterministic downstream filtering, and fails closed
  when required facts are missing or criteria are unmet.
- Updated rendering to expose adjudication status, the downstream filter disease,
  any supported diagnostic label, and the cards driving a changed major category.
- Bumped all working and accepted schemas; prior in-flight artefacts require
  re-ingestion rather than migration.

## 0.1.1

- Replaced central phase queues with independent `work/<paper-id>/` folder state.
- Moved complete, generated phase instructions to committed `prompts/` data.
- Added deterministic fan-out, source-aware confirmation, and accept-only incorporation.
- Made final packages identify the exact provisional round independently audited.
- Removed provisional corpus semantics; corpus membership now implies completed audit.
- Added per-paper incorporation rejection while keeping global identity collisions fatal.
- Separated private input, work, acceptance, and archive data from shipped `output/` artefacts.

## 0.1.0

Initial release of the corpus-grounded evidence layer for myeloid NGS interpretation.

- Publication selection - Identifies the next indexed publication and ingestion phase to process.
- Phased ingestion - Prepares and accepts bounded census, extraction, and independent audit handoffs.
- Evidence validation - Checks schemas, census completeness, source-verbatim quotes, and audit requirements.
- Extraction rework - Returns failed audits to a controlled Phase 2 correction round while preserving provenance.
- Corpus building - Incorporates accepted packages into deterministic provisional or audited corpus and index files.
- Evidence retrieval - Selects gene- and disease-matched cards and reports genes the corpus cannot assess.
- Evidence rendering - Produces a deterministic, citable Markdown evidence block within a token budget.
- Citation key generation - Builds stable publication identifiers and display citations from citation metadata.
- Vocabulary validation - Enforces the closed disease vocabulary and required umbrella relationships.