# Prognosis owner — atomic reasoning

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

Use only the supplied owner pack. Return prognosis propositions as atomic literature rules, patient-state applications and deterministic conclusion logic.

Rules:
- Patient facts are immutable. Reference supplied case_fact_ids and variant_ids only.
- Separate framework applicability, framework rule, patient/derived state, rule application and final prognostic proposition.
- Each literature rule may propose supporting card tags only from this owner's candidate-card envelope. Use [] when no supplied card supports the rule.
- Every rule must set `direct_requirement`. Use null unless the literature rule itself states an exact fact kind and expected value that can be audited verbatim. A direct patient application is permitted only against that audited requirement.
- Use a derived_state only when applicability requires semantic composition of supplied facts. Do not create a derived_state for a direct exact fact match.
- `mode: direct` is allowed only with one explicit `direct_match` whose expected_value can be compared exactly with the supplied case fact. Otherwise use `mode: semantic` and `direct_match: null`.
- For framework-based propositions populate `framework`; its applicability_application_id must reference an application in the same proposition.
- Python will audit evidence, audit semantic applicability, and evaluate conclusion logic. Do not treat your proposed statuses as final.
- Use `P-` prefixes for proposition, rule, state and application IDs.

## Deterministic feedback from a prior rejected owner attempt
{{ input.audit_feedback }}

## Owner pack
{{ input.owner_pack }}
