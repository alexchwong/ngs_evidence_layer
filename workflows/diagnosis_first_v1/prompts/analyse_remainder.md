# Prototype downstream reporting analysis

## Task

Answer every rule supplied in `reporting-rules-remainder.md` using the patient case, `ngs-panel-scope.md`, and the evidence made available for this pass.

`reporting-rules-remainder.md` is the prompt-owned analysis contract rendered for this pass. Follow its patient-level conclusion style, REPORT/OMIT taxonomy, evidence boundary, branch-specific scope, and canonical reporting rules exactly. Apply the **Rule-draft citation contract** in `citation_rules.md`.

## Branch semantics

The supplied rules deterministically define the branch:

- If the rule file begins at R2, the Step-3 CMC was unchanged. Use `report-draft-dx.md` as the completed R0/R1 diagnostic conclusion and answer only R2-R5. Do not redo diagnosis.
- If the rule file includes R0 and R1, the Step-3 CMC changed. Re-answer R0-R5 from scratch using `downstream_evidence.md`; its diagnosis section contains all diagnosis cards from both the Step-1 and Step-3 CMCs plus detected-gene diagnosis cards.

The Step-3 refined CMC shown in `downstream_evidence.md` is fixed for this step. **Do not change, re-route, propose, or emit another CMC.** A WHO-5/ICC diagnosis may be refined within that broad category, but the CMC routing decision is closed.

## Reporting-rule output

- Answer each supplied rule exactly once and in source order.
- Write exactly one line per rule using: `R<section>.<number> REPORT: ...` or `R<section>.<number> OMIT: ...`.
- If R0.1 is supplied, it is mandatory `REPORT:` patient-result content and must end with `(no citation required)`.
- `REPORT:` text must be direct report-ready clinical prose, not report-construction meta-language.
- Use `ngs-panel-scope.md` to resolve negative gene findings from a complete NGS result. If a listed panel gene is absent from the detected-variant list, treat it as negative only for the variant classes defined by that file; do not leave that gene unresolved merely because it is unlisted.
- Use only runtime card tags copied from `downstream_evidence.md`.

## Validation repair

If validation fails, repair only the rule(s) and defect(s) identified by the validator. For citation defects, use `downstream_evidence.md` as the only evidence source for replacement runtime tags. Do not inspect private JSON/tag maps, the combined `evidence.md`, or corpus files.

## Output contract

Return only the requested reporting-rule lines. No headings, bullets, blank lines, code fences, commentary, or `REFINED_CMC:` line.
