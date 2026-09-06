# Second diagnosis — clinical reasoning

Assess only whether a concurrent/second haematological diagnosis is established or meaningfully signalled. Do not match evidence cards and do not construct the internal reasoning graph.

Return one YAML mapping only:

```yaml
authority: second_diagnosis
diagnosis:
  label: <concurrent diagnosis or "none">
  schema_disease: null
  diagnostic_effect: unchanged
  status: <established|signal|none>
  variant_assessments:
    - variant_id: <supplied source variant ID, e.g. V1>
      classification: <diagnostic_for_primary|nonspecific|diagnostic_for_other_pathology>
      other_pathology: null
      reason: <concise clinical reason>
reasoning:
  - rule: <one atomic framework rule relevant to the possible second diagnosis>
    case_fact_ids: []
    variant_ids: []
    assessment: <met|not_met|unknown>
    supports_conclusion: true
    reason: <apply the rule to this patient>
conclusion:
  operator: all_of
reason: <concise integrated clinical reason>
```

Rules:
- Use only the supplied case and reference material.
- Do not cite, select, rank or mention evidence cards. A separate evidence matcher owns that task.
- Do not create reasoning IDs or internal graph IDs; Python assigns all machine identifiers after this pass.
- `established` requires a complete patient-specific reasoning basis; mark the defining reasoning point(s) with `supports_conclusion: true`.
- `signal` means consideration is warranted but the supplied facts do not establish the diagnosis.
- `none` means no concurrent diagnosis is proposed; no reasoning point needs to support a second-diagnosis conclusion.
- Return exactly one variant assessment for every supplied variant.
- Every atomic `reasoning` row must retain all six fields: `rule`, `case_fact_ids`, `variant_ids`, `assessment`, `supports_conclusion`, and `reason`.
- `supports_conclusion: true` is valid only when that same row has `assessment: met`.
- On a feedback redo, change only the object(s) implicated by the deterministic feedback unless correcting that object logically requires a linked field in the same object to change. Preserve all unrelated clinical decisions.

## Feedback from a prior clinical-reasoning attempt
{{ input.audit_feedback }}

## Owner pack
{{ input.owner_pack }}
