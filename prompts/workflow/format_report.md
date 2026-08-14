# Format the final report safely

## Task

Transform `report-draft.md` into the final clinical report while preserving the workflow's deterministic citation contract. Apply the selected formatting prompt only within these constraints.

## Task-specific rules

- `report-draft.md` is the sole source of report content.
- Treat explicit drafting instructions in `report-draft.md` as constraints, not report prose. Apply instructions such as `Omit ...`, `Do not state ...`, and `Do not infer ...`, then omit the instruction itself from the final report.
- Do not introduce a clinical assertion, qualification, recommendation, citation, patient fact, or interpretation absent from `report-draft.md`.
- For every retained statement, copy verbatim every exact `[card:<six-character-tag>]` marker associated with its supporting facts and keep those markers attached to the facts they support.
- When combining retained draft statements, copy all supporting markers verbatim and adjacently.
- Do not create, infer, alter, shorten, parse, replace, or renumber a card-tag marker.
- Retain `(no citation required)` for every retained sentence carrying that marker.
- Do not write numeric citations.
- Do not write a `## References` section or bibliography; deterministic Step 6C performs citation replacement and bibliography rendering.

The selected formatting prompt controls report length, ordering, emphasis, compression, and optional-content choices only when those instructions do not conflict with this prompt.

## Output contract

Return only the final report Markdown for `report-final.md`.

## Final check

Before returning, verify privately that every clinical statement is traceable to `report-draft.md`, every retained card marker is copied exactly, no new marker was created, and no deterministic citation rendering has been attempted.
