# Categorical final-summary synthesis

## Task

Complete exactly one deterministic category-summary YAML artifact in a fresh bounded model session. This is a category-isolated synthesis step, not final Markdown formatting.

Use the full patient context supplied to the step to understand the case. The reportable assertions for the assigned category are the `omit: false` rules for that category in `report-draft.yaml`; do not resurrect an `omit: true` rule merely because it is visible in `report-draft-remainder.yaml` or another context file.

## Integration and category isolation

- Answer only the assigned category. Do not spend its word budget summarising another category.
- Synthesize the reportable source statements into a patient-level clinical conclusion rather than shortening or paraphrasing each source line separately.
- Preserve clinically material qualifications, uncertainty and conditionality.
- A single integrated diagnosis is preferred; use two or more diagnoses only when the source rules support multiple pathologies.
- There is no separate `detected_variants` final category. Detected variants belong in the diagnosis paragraph.
- The full-context files are interpretive context, not permission to introduce a report assertion absent from the assigned category's reportable rules.

## Citation provenance

Apply `workflows/categorical_v1/prompts/citation_rules.md` exactly. Keep `text` and `citation` separate. When source facts with different citation dispositions cannot be truthfully represented by one citation field, use separate complete sentences while keeping the paragraph integrated.

## Output contract

Modify only the category YAML named by the workflow step. Preserve `schema_version`, `category`, and `statements`. Each completed statement contains exactly `text` and `citation` and is a full sentence ending in a full stop.

Return no Markdown report, headings, bibliography, numeric citations, code fences, or commentary.
