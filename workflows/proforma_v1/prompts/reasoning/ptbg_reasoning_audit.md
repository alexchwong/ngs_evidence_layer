# PTBG patient-applicability reasoning audit

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

Assess every supplied semantic derived state and semantic application using only the supplied evidence-approved rules and supplied patient facts.

Rules:
- Do not search for or choose literature.
- Do not invent patient facts.
- Do not change a rule because the patient does not satisfy it.
- Return one derived_state result for every supplied derived-state item and one criteria result for every supplied semantic application. The criteria criterion_id is the supplied application_id.
- Direct exact applications are intentionally absent; Python evaluates those deterministically.
- Do not decide final reportability. Python evaluates proposition logic after this audit.

## Deterministic feedback from a prior invalid reasoning artifact
{{ input.audit_feedback }}

## Reasoning items
{{ input.reasoning_items }}
