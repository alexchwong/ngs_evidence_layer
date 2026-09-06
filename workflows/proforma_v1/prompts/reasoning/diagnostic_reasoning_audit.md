# Diagnostic patient-applicability reasoning audit

## Output serialization contract
Return exactly one YAML mapping conforming to the declared schema. Return YAML only: no Markdown headings, no tables, no prose outside the mapping, no code fence around the answer, and no `---` document separators. The example below shows serialization/shape only; replace placeholders with your actual answer.

```yaml
derived_states:
  - state_id: <exact supplied state_id>
    status: <supported|unsupported|indeterminate>
    value: <audited value or null>
    case_fact_ids: []
    comments: []
criteria:
  - criterion_id: <exact supplied criterion/application ID>
    status: <met|not_met|unknown>
    case_fact_ids: []
    comments: []
```

Use only the supplied evidence-approved rules and supplied patient facts/variants. Do not search for evidence and do not compare WHO against ICC.

For every supplied derived state, determine whether the proposed value is supported by the cited patient facts. For every supplied criterion, determine whether this patient meets the evidence-approved rule. Return all results in one artifact.

Do not evaluate the final Boolean root and do not choose the final diagnosis; Python does that after this audit.

## Deterministic feedback from a prior invalid reasoning-audit result
{{ input.audit_feedback }}

## Audit items
{{ input.reasoning_items }}
