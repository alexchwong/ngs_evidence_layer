# Diagnosis-first reporting analysis

## Task

Answer every rule supplied in `reporting-rules-dx.md` using the patient case, `diagnostic_evidence.md`, and `ngs-panel-scope.md`, then make one broad case-major-category routing decision.

`reporting-rules-dx.md` is the prompt-owned analysis contract for this pass. The workflow-local reporting policy embedded in this rule view uses REPORT/OMIT terminology; encode REPORT as `omit: false` and OMIT as `omit: true` in the YAML template. Apply `workflows/categorical_v1/prompts/citation_rules.md`.

## YAML draft

Modify the existing deterministic `<work-dir>/report-draft-dx.yaml` template only.

- Preserve every rule ID and rule order.
- Every rule must retain at least one atomic statement, including omitted rules.
- Add statement items when a rule requires more than one independently citable fact.
- `text` contains only the assertion prose; `citation` contains only its citation disposition.
- `R0.1` remains `omit: false` with `(no citation required)`.
- Apply the supplied molecular findings to the clinical, morphological and other case facts. Do not diagnose a neoplasm or germline state from VAF alone.
- Use `ngs-panel-scope.md` to resolve negative gene findings from a complete NGS result only within the variant classes defined by that file.
- Use only runtime card tags copied from `diagnostic_evidence.md`.

## Refined CMC

Set the top-level `refined_cmc` field to exactly one value copied from `case-major-categories.json`.

- This is a broad retrieval-routing category, not the WHO-5 or ICC diagnostic label.
- Keep the Step-1 CMC unless the R1 analysis supports routing the case to a different broad category.
- Do not add an explanation or citation to `refined_cmc`.

## Validation repair

If validation fails, repair only the rule(s), statement(s), or field identified by the validator. For citation defects, use `diagnostic_evidence.md` as the only evidence source for replacement runtime tags. Do not inspect private JSON/tag maps, corpus files, or validator source.

## Output contract

Write only the modified `report-draft-dx.yaml` file. Do not create a second draft, Markdown rule list, code fence, or commentary.
