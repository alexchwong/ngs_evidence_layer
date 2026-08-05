# NEWS

## 0.1.3

- Allowed multi-part quoting, introduced as evidence bundles (`contiguous_text`, `composite_text`, `table_relation`) using verbatim, role-tagged fragments mapped via `support_map`.
- Changed Phase 3 to emit one complete pass/fail review per card, including failure type, defensibility, guidance, and quote restatement for failures; mandatory audit checks added.
- Added Phase 4 human adjudication as the sole creator of `paper.final.json` and
  removed the Phase 3 to Phase 2 rework loop.
- Changed validation to focus only on the final json. Errors in upstream jsons return warnings
- Separated exact card diseases from corpus-broadening `disease_ancestors` derived from a cycle-checked umbrella graph.
- Extended the disease vocabulary to 1.2 with `MPN`, `MDS/MPN`, `MPN blast phase`,
  `acute leukaemia of ambiguous lineage`, `histiocytic/dendritic neoplasm`, and
  `haematological malignancy, other`, and re-parented the affected families.
- `publication_type` limited to 6 categorical possibilities.
- Added `publication_type_verified_by_phase3` and removed `escalates_to` from cards,
  the index, and retrieval
- Added `scripts/transport.py` to move private corpus files between computers
- Optimized `SKILL.md` as a deny-by-default six-step case-reporting workflow with
  declared inputs and one output per step, complete-test-result semantics, and
  absent cytogenetics recorded as a declared assumption rather than a result.

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