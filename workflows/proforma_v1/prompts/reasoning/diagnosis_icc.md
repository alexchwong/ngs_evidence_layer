# ICC diagnosis — clinical reasoning

Reason only about the ICC diagnosis. Do not match evidence cards and do not construct the workflow's internal reasoning graph.

Return one YAML mapping only using this shape:

```yaml
authority: icc
diagnosis:
  label: <ICC diagnosis>
  schema_disease: null
  diagnostic_effect: <unchanged|refined|superseded>
  status: established
  variant_assessments:
    - variant_id: <supplied source variant ID, e.g. V1>
      classification: <diagnostic_for_primary|nonspecific|diagnostic_for_other_pathology>
      other_pathology: null
      reason: <concise clinical reason>
reasoning:
  - rule: <one atomic ICC/framework rule relevant to the conclusion>
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
- Assess ICC independently; do not assume WHO5 is correct.
- Use only supplied case facts, source-facing variant IDs and reference material.
- Do not cite, select, rank or mention evidence cards. Evidence matching is a separate pass.
- Keep rules atomic and put patient-specific application in `assessment` and `reason`.
- Do not create reasoning IDs or internal graph IDs; Python assigns all machine identifiers after this pass.
- Set `supports_conclusion: true` only on the minimal reasoning points that define/support the proposed diagnosis, and only when their assessment is `met`.
- Return exactly one variant assessment for every supplied variant.
- `status` must be `established`. `schema_disease` is normally null, except use `no_haematological_malignancy` when that is the explicit ICC outcome.

## Feedback from a prior clinical-reasoning attempt
{{ input.audit_feedback }}

## Owner pack
{{ input.owner_pack }}
