# Format the final report safely

## Task

Transform `report-draft.md` into the final clinical report while preserving the workflow's deterministic citation contract. Apply the selected formatting prompt only within these constraints.

## Task-specific rules

- `report-draft.md` is the sole source of report content.
- Treat explicit drafting instructions in `report-draft.md` as constraints, not report prose. Apply instructions such as `Omit ...`, `Do not state ...`, and `Do not infer ...`, then omit the instruction itself from the final report.
- Do not introduce a clinical assertion, qualification, recommendation, citation, patient fact, or interpretation absent from `report-draft.md`.
- Citation dispositions are part of the source assertion, not optional annotations. For every retained statement, preserve its citation disposition.
- For every retained statement supported by cards, copy verbatim every exact `[card:<six-character-tag>]` marker associated with its supporting facts and keep those markers attached to the facts they support.
- When combining retained draft statements, take the union of all supporting card markers and copy all of them verbatim and adjacently. Never discard a marker merely because another retained marker appears to support the same sentence.
- Do not create, infer, alter, shorten, parse, replace, or renumber a card-tag marker.
- Retain `(no citation required)` for every retained sentence carrying that disposition.
- Patient-specific factual summaries derived from `report-draft.md`, including a formatting prompt's required opening variant-summary sentence, may use `(no citation required)` when the supporting draft content carries that disposition; do not invent literature citations for patient-result facts.
- Every sentence that ends in a full stop MUST place its complete citation disposition immediately after that full stop, separated by one space: `.... [card:abcdef]`, `.... [card:abcdef][card:123456]`, or `.... (no citation required)`. The required order is always `sentence` → `.` → one space → `citation disposition`. Do not write `... [card:abcdef].` or `... (no citation required).`.
- Citation preservation takes precedence over formatting, compression, and word-count targets. If preserving the required citation disposition conflicts with a style or length instruction, preserve the citation disposition.
- Do not write numeric citations.
- Do not write a `## References` section or bibliography; deterministic Step 6C performs citation replacement and bibliography rendering.

The selected formatting prompt controls report length, ordering, emphasis, compression, and optional-content choices only when those instructions do not conflict with this prompt.

## Output contract

Return only the final report Markdown for `report-final.md`.

## Final check

Before returning, verify privately that every clinical statement is traceable to `report-draft.md`, every retained citation disposition is preserved, merged statements contain the union of their supporting markers, every sentence-ending full stop is immediately followed by one space and its citation disposition, no marker appears before the full stop, no new marker was created, and no deterministic citation rendering has been attempted.
