# NEWS

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