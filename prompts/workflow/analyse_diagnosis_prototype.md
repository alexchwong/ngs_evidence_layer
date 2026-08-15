# Prototype diagnosis-first reporting analysis

## Task

Answer every rule supplied in `reporting-rules-dx.md` using the patient case and `diagnostic_evidence.md`, then make one broad case-major-category routing decision.

## Reporting-rule output

- Answer each supplied rule exactly once and in source order.
- Write exactly one line per rule using: `R<section>.<number> REPORT: ...` or `R<section>.<number> OMIT: ...`.
- `R0.1` is mandatory `REPORT:` patient-result content and must end with `(no citation required)`.
- `REPORT:` text must be direct report-ready clinical prose, not an instruction about what the final report should say.
- Use `OMIT:` when the topic has no reportable case-specific implication; do not use `OMIT:` merely because the answer is negative if that negative finding materially changes the diagnosis or differential.
- Apply the supplied molecular findings to the clinical, morphological and other case facts. Do not diagnose a neoplasm or germline state from VAF alone.
- Use `diagnostic_evidence.md` as the complete literature-evidence boundary for the supplied R0/R1 rules. It intentionally includes broad diagnosis cards from the Step-1 CMC, diagnosis cards matching detected genes, and gene-matched germline cards.
- Follow `citation_rules.md` exactly. Copy runtime card tags only from `diagnostic_evidence.md`.

## Refined CMC routing decision

After all R0/R1 lines, write exactly one final line:

`REFINED_CMC: <case major category>`

- The value must be copied exactly from `case-major-categories.json`.
- This is a broad retrieval-routing category, not the WHO-5 or ICC diagnostic label.
- Keep the Step-1 CMC unless the R1 analysis supports routing the case to a different broad category.
- A CMC change does not need to settle every downstream reporting question; it only needs to identify the correct broad evidence-retrieval family.
- Do not append punctuation, a citation, explanation, or any other text to the `REFINED_CMC:` line.

## Validation repair

If validation identifies a citation defect, repair only the affected rule line and use `diagnostic_evidence.md` as the only evidence source for replacement runtime tags. Do not inspect private JSON/tag maps or corpus files.

## Output contract

Return only the R0/R1 rule lines followed by the single `REFINED_CMC:` line. No headings, bullets, blank lines, code fences, or commentary.
