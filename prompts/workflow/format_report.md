# Format the final report safely

## Task

Transform `report-draft.md` into the final clinical report. Apply the selected formatting prompt only within the source-integrity, omission, and shared citation constraints below.

## Task-specific rules

- `report-draft.md` is the sole source of report content.
- Follow `prompts/workflow/citation_rules.md` exactly. Citation integrity takes precedence over formatting, compression, and word-count targets.
- Every draft line is explicitly classified after its rule ID as either `REPORT:` or `OMIT:`.
- Only text after `REPORT:` is eligible source prose for the final report. Strip the rule ID and `REPORT:` token when rendering it.
- `R0.1 REPORT:` content is mandatory final-report content. Render it as a standalone variant-result sentence and preserve its `(no citation required)` disposition; do not merge it with literature-supported interpretation.
- Treat every `OMIT:` line as an instruction, not report prose. Apply the omission and do not reproduce, paraphrase, negate, explain, summarise, or otherwise surface any text after `OMIT:` in the final report.
- Do not independently reinterpret whether a negative statement should be reported. Step 6A has already made the report-versus-omit decision: `REPORT:` is eligible report content; `OMIT:` is not.
- Do not introduce a clinical assertion, qualification, recommendation, citation, patient fact, or interpretation absent from `report-draft.md`.
- When combining retained draft assertions, preserve the union of all runtime card markers supporting the retained facts exactly as required by `citation_rules.md`. Never editorially select a smaller citation set because one card appears sufficient.
- When splitting a retained draft assertion into multiple sentences, give each resulting sentence the citation disposition required for the facts it retains.
- Do not create, infer, alter, shorten, parse, replace, translate, or renumber a card-tag marker.
- Do not write numeric citations.
- Do not write a `## References` section or bibliography; deterministic Step 6C performs citation replacement and bibliography rendering.

The selected formatting prompt controls report length, ordering, emphasis, compression, and optional-content choices only when those instructions do not conflict with this prompt or `citation_rules.md`.

### Prognostic interpretation

Synthesize retained prognostic assertions into concise, framework-led report prose.

- State the applicable prognostic framework and risk category first when available.
- Combine variants with the same prognostic effect into a single clause or sentence.
- After describing variants that affect prognosis, collectively summarise detected variants that make no additional prognostic contribution under that framework when this is useful.
- Do not repeat the framework name for every variant.
- Do not preserve the one-rule-one-answer structure of the source assertions.
- Prefer one or two information-dense sentences over a variant-by-variant list.
- Preserve the distinction between:
  - prognostic effects defined by the formal framework; and
  - prognostic evidence derived from studies outside that framework.
- When a variant has material disease-specific prognostic evidence outside the framework, report this after the framework-based conclusion.
- Omit discussion of variants outside the framework when the retained assertions provide no material additional prognostic effect.

## Output contract

Return only the final report Markdown for `report-final.md`.

## Final check

Before returning, verify privately that every clinical statement is traceable to `REPORT:` content in `report-draft.md`; all rule IDs and `REPORT:`/`OMIT:` tokens have been removed from final prose; no `OMIT:` instruction has been surfaced or paraphrased; merged and split sentences preserve the citation provenance required by `citation_rules.md`; no runtime tag was altered or newly created; and no deterministic citation rendering has been attempted.
