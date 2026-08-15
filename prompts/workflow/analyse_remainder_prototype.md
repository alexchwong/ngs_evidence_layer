# Prototype downstream reporting analysis

## Task

Answer every rule supplied in `reporting-rules-remainder.md` using the patient case and the evidence made available for this pass.

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
- Use `OMIT:` for a topic that should not appear in the final report. Do not convert a clinically meaningful negative finding into an omission instruction.
- State the patient-level conclusion first, then any material qualifier, condition, exception or limitation.
- Use only `downstream_evidence.md` for literature support in this pass. When the unchanged-CMC branch supplies `report-draft-dx.md`, treat it as prior patient-level diagnostic conclusions, not as a source of new runtime citation tags.
- Follow `citation_rules.md` exactly and copy runtime card tags only from `downstream_evidence.md`.

## Validation repair

If validation identifies a citation defect, repair only the affected rule line and use `downstream_evidence.md` as the only evidence source for replacement runtime tags. Do not inspect private JSON/tag maps, the combined `evidence.md`, or corpus files.

## Output contract

Return only the requested reporting-rule lines. No headings, bullets, blank lines, code fences, commentary, or `REFINED_CMC:` line.
