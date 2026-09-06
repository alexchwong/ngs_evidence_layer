# Biomarker / MRD owner — atomic reasoning

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

Use only the supplied owner pack. Return follow-up-marker propositions as atomic literature rules plus patient applicability.

Rules:
- Patient facts are immutable. Reference supplied case_fact_ids and variant_ids only.
- Assign only candidate cards supplied in this owner pack.
- Every rule must set `direct_requirement`. Use null unless the literature rule itself states an exact fact kind and expected value that can be audited verbatim. A direct patient application is permitted only against that audited requirement.
- Prefer direct exact applicability for simple present/absent marker requirements. Use semantic applicability only when the marker proposition requires non-trivial composition.
- Do not infer longitudinal persistence, clearance or assay performance not supplied in the case.
- Python independently audits evidence and applicability before reporting.
- Use `B-` prefixes for proposition, rule, state and application IDs.
- `framework` should normally be null. `worksheet` should normally be [].

## Deterministic feedback from a prior rejected owner attempt
{{ input.audit_feedback }}

## Owner pack
{{ input.owner_pack }}
