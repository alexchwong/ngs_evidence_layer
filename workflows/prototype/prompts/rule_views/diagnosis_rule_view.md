# Diagnosis-pass reporting rules

## Task

Answer R0-R1 only. Produce self-contained patient-level conclusions suitable for later report synthesis. After these rule answers, the workflow prompt separately requires one refined CMC routing line; that routing line is not report content.

{{REPORTING_RULE_POLICY}}

## Evidence boundary

Treat `diagnostic_evidence.md` as the complete literature-evidence boundary for this pass. Use only runtime card tags exposed there.

## Citation contract

Apply the **Rule-draft citation contract** in `prompts/workflow/citation_rules.md`. The rule-draft citation contract, not the final-report sentence contract, governs these rule answers.

{{CANONICAL_RULES}}
