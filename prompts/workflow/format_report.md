# Format the final report safely

## Task

Transform `report-draft.md` into the final clinical report. Apply the selected formatting prompt only within the source-integrity, omission, and shared citation constraints below.

## Task-specific rules

- `report-draft.md` is the sole source of report content.
- Follow `prompts/workflow/citation_rules.md` exactly. Citation integrity takes precedence over formatting, compression, and word-count targets.
- Every draft line is explicitly classified after its rule ID as either `REPORT:` or `OMIT:`.
- Only text after `REPORT:` is eligible source prose for the final report. Strip the rule ID and `REPORT:` token when rendering it.
- Treat every `OMIT:` line as an instruction, not report prose. Apply the omission and do not reproduce, paraphrase, negate, explain, summarise, or otherwise surface any text after `OMIT:` in the final report.
- Do not independently reinterpret whether a negative statement should be reported. Step 6A has already made the report-versus-omit decision: `REPORT:` is eligible report content; `OMIT:` is not.
- Do not introduce a clinical assertion, qualification, recommendation, citation, patient fact, or interpretation absent from `report-draft.md`.
- When combining retained draft assertions, preserve the union of all runtime card markers supporting the retained facts exactly as required by `citation_rules.md`. Never editorially select a smaller citation set because one card appears sufficient.
- When splitting a retained draft assertion into multiple sentences, give each resulting sentence the citation disposition required for the facts it retains.
- Do not create, infer, alter, shorten, parse, replace, translate, or renumber a card-tag marker.
- Do not write numeric citations.
- Do not write a `## References` section or bibliography; deterministic Step 6C performs citation replacement and bibliography rendering.

The selected formatting prompt controls report length, ordering, emphasis, compression, and optional-content choices only when those instructions do not conflict with this prompt or `citation_rules.md`.

## Output contract

Return only the final report Markdown for `report-final.md`.

## Final check

Before returning, verify privately that every clinical statement is traceable to `REPORT:` content in `report-draft.md`; all rule IDs and `REPORT:`/`OMIT:` tokens have been removed from final prose; no `OMIT:` instruction has been surfaced or paraphrased; merged and split sentences preserve the citation provenance required by `citation_rules.md`; no runtime tag was altered or newly created; and no deterministic citation rendering has been attempted.
