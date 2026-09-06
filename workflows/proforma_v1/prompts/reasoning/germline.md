# Germline — clinical reasoning

Assess whether each supplied molecular finding creates sufficient patient-specific suspicion of constitutional predisposition to justify dedicated germline evaluation. Do not match evidence cards and do not construct internal graph IDs.

Return one YAML mapping only:

```yaml
domain: germline
variant_assessments:
  - variant_id: V1
    eligibility: <assess|skip_no_predisposition_evidence>
    predisposition_evidence: <inherited mechanism supported by supplied reference material or null>
    event_compatibility: {status: <supportive|consistent|discordant|not_supplied|not_assessable>, reason: <...>}
    age: {status: <supportive|consistent|discordant|not_supplied|not_assessable>, reason: <...>}
    vaf: {status: <supportive|consistent|discordant|not_supplied|not_assessable>, reason: <...>}
    personal_history: {status: <supportive|consistent|discordant|not_supplied|not_assessable>, reason: <...>}
    family_history: {status: <supportive|consistent|discordant|not_supplied|not_assessable>, reason: <...>}
    phenotype: {status: <supportive|consistent|discordant|not_supplied|not_assessable>, reason: <...>}
    bucket: <germline_suspicious|germline_against|germline_uncertain|null>
    reason: <integrated patient-specific conclusion>
    reasoning:
      - rule: <atomic inherited-predisposition rule>
        case_fact_ids: []
        variant_ids: [V1]
        assessment: <met|not_met|unknown>
        supports_conclusion: true
        reason: <patient-specific application>
```

Rules:
- Every supplied variant must appear exactly once.
- Eligibility is corpus-bounded. Use `skip_no_predisposition_evidence` when supplied reference material does not establish a relevant inherited-predisposition association; then all six factor fields and `bucket` should be null in the final normalized artifact.
- For `assess`, explicitly assess event compatibility, age, VAF, personal history, family history and phenotype.
- `supportive` increases suspicion; `consistent` is neutral; `discordant` weighs against; missing data are `not_supplied`; supplied but uninterpretable data are `not_assessable`.
- Do not use universal age or VAF thresholds.
- Gene predisposition and event compatibility alone are insufficient for `germline_suspicious`.
- `germline_suspicious` requires the overall patient-specific evidence to positively support constitutional origin. Discordant factors must genuinely weigh against this bucket.
- `germline_against` is appropriate when the overall evidence weighs against constitutional origin even if germline origin cannot be absolutely excluded.
- `germline_uncertain` is for genuinely indeterminate/competing evidence, not merely because constitutional testing has not yet occurred.
- Do not claim confirmed germline status.
- Use only supplied patient facts, source-facing variant IDs, authoritative diagnosis and reference material.
- Do not cite or mention evidence cards. Evidence matching is separate.
- Every atomic `reasoning` row must retain all six fields: `rule`, `case_fact_ids`, `variant_ids`, `assessment`, `supports_conclusion`, and `reason`.
- `supports_conclusion: true` is valid only when that same row has `assessment: met`.
- On a feedback redo, change only the object(s) implicated by the deterministic feedback unless correcting that object logically requires a linked field in the same object to change. Preserve unrelated germline decisions and factor assessments.

## Feedback from a prior clinical-reasoning attempt
{{ input.audit_feedback }}

## Owner pack
{{ input.owner_pack }}
