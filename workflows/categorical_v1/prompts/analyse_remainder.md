# Diagnosis-first downstream reporting analysis

## Task

Answer every rule supplied in `reporting-rules-remainder.md` using the patient case, `ngs-panel-scope.md`, and the evidence made available for this pass.

`reporting-rules-remainder.md` is the prompt-owned analysis contract for this pass. The workflow-local reporting policy embedded in this rule view uses REPORT/OMIT terminology; encode REPORT as `omit: false` and OMIT as `omit: true` in the YAML template. Apply `workflows/categorical_v1/prompts/citation_rules.md`.

## Branch semantics

The supplied rules deterministically define the branch:

- If the rule file begins at R2, the Step-3 CMC was unchanged. `reporting-rules-remainder.md` contains the completed `report-summary-dx.yaml` injected as established R0/R1 patient-level diagnostic context; use that context and answer R2-R5.
- If the rule file includes R0 and R1, the Step-3 CMC changed. Re-answer R0-R5 from scratch using `downstream_evidence.md`; its diagnosis section contains the recalled diagnosis evidence required for this branch.

The Step-3 refined CMC is fixed. Do not change, re-route, propose, or emit another CMC.

## YAML draft

Modify the existing deterministic `<work-dir>/report-draft-remainder.yaml` template only.

- Preserve every rule ID and rule order.
- Every rule must retain at least one atomic statement, including omitted rules.
- Add statement items when a rule requires more than one independently citable fact.
- `text` contains only the assertion prose; `citation` contains only its citation disposition.
- If R0.1 is present, keep it `omit: false` with `(no citation required)`.
- Use `ngs-panel-scope.md` to resolve negative panel-gene findings only within the assay classes defined there.
- Use only runtime card tags copied from `downstream_evidence.md`.

## Validation repair

If validation fails, repair only the rule(s), statement(s), or field identified by the validator. For citation defects, use `downstream_evidence.md` as the only evidence source for replacement runtime tags. Do not inspect private JSON/tag maps, combined `evidence.md`, corpus files, or validator source.

## Output contract

Write only the modified `report-draft-remainder.yaml` file. Do not create Markdown rule lines, code fences, commentary, or a new refined-CMC field.
