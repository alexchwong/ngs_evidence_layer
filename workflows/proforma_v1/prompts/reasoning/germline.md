# Germline owner — atomic reasoning

## Output serialization contract
Return exactly one YAML mapping conforming to the declared schema. Return YAML only: no Markdown headings, no tables, no prose outside the mapping, no code fence around the answer, and no `---` document separators. The example below shows serialization/shape only; replace placeholders with your actual answer.

```yaml
domain: <prognosis|treatment|biomarker|germline>
propositions:
  - proposition_id: <stable proposition ID>
    bucket: <domain bucket>
    text: <reportable proposition>
    reason: <reason>
    variant_ids: []
    reportable: true
    rules:
      - rule_id: <stable rule ID>
        statement: <one atomic literature rule>
        evidence_required: true
        proposed_card_tags: []
        direct_requirement: null
    derived_states: []
    applications:
      - application_id: <stable application ID>
        rule_ids: []
        case_fact_ids: []
        state_ids: []
        mode: semantic
        direct_match: null
        proposed_status: <met|not_met|unknown>
        reason: <reason>
    conclusion:
      operator: all_of
      application_ids: []
    framework: null
    worksheet: []
```

Use only the supplied owner pack. Preserve the factorised germline worksheet while separating literature rules from patient-specific factor interpretation.

Rules:
- Patient facts are immutable. Reference supplied case_fact_ids and variant_ids only.
- Literature/predisposition rules require supporting cards from the supplied candidate-card envelope.
- Every rule must set `direct_requirement`. Use null unless the literature rule itself states an exact fact kind and expected value that can be audited verbatim. A direct patient application is permitted only against that audited requirement.
- Patient factors such as event compatibility, age, VAF, personal history, family history and phenotype are applications of supplied facts; do not turn them into literature claims.
- Use semantic applications for factors requiring clinical interpretation. Use direct exact applicability only where the expected value is literally testable from one supplied fact.
- `worksheet` must contain exactly one row for each canonical factor: `predisposition_evidence`, `event_compatibility`, `age`, `vaf`, `personal_history`, `family_history`, `phenotype`. Never omit a factor; use `not_supplied` or `not_assessable` when appropriate.
- Each worksheet row must use one status: `supportive` (actively supports germline suspicion), `consistent` (compatible but not independently supportive), `discordant` (weighs against the proposed germline interpretation), `not_supplied`, or `not_assessable`.
- Patient-factor rows with `supportive`, `consistent`, or `discordant` must reference the application used to interpret that supplied factor. `application_id` may be null for `not_supplied` / `not_assessable` factors and for `predisposition_evidence`, whose literature support is audited separately.
- Use only the canonical germline buckets `germline_suspicious`, `germline_against`, or `germline_uncertain`.
- Do not use a hidden numeric score. Python checks consistency only; the owner proposes the clinical bucket and the independent reasoning audit checks the factors.
- Use `G-` prefixes for proposition, rule, state and application IDs.
- `framework` should normally be null.

## Deterministic feedback from a prior rejected owner attempt
{{ input.audit_feedback }}

## Owner pack
{{ input.owner_pack }}
