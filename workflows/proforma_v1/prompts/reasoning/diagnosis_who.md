# WHO5 diagnosis — clinical reasoning

Reason only about the diagnosis. Do not match evidence cards and do not construct the workflow's internal reasoning graph.

Return one YAML mapping only:

```yaml
authority: who5
diagnosis:
  label: <WHO5 diagnosis>
  schema_disease: <WHO5 schema disease>
  diagnostic_effect: <unchanged|refined|superseded>
  status: established
  variant_assessments:
    - variant_id: <supplied source variant ID, e.g. V1>
      classification: <diagnostic_for_primary|nonspecific|diagnostic_for_other_pathology>
      other_pathology: null
      reason: <concise clinical reason>
reasoning:
  - rule: <one atomic WHO5/framework rule relevant to the conclusion>
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
- Use only the supplied case and reference material. Do not use outside literature.
- Patient observations are immutable. Reference only supplied `C...` fact IDs and source-facing variant IDs such as `V1`.
- The authoritative starting diagnosis is `owner_pack.structured_case.provisional_disease`. It is immutable across retries.
- Set `diagnostic_effect` only by comparing the proposed `diagnosis.label` with that authoritative starting diagnosis. Never compare against, or treat as baseline, a diagnosis from a prior failed/retried model answer.
- If the proposed diagnosis is the same clinical diagnosis as the authoritative starting diagnosis, set `diagnostic_effect: unchanged`, including when a prior failed attempt proposed a different diagnosis.
- Use `refined` or `superseded` only when the final proposed diagnosis genuinely changes the authoritative starting diagnosis and the supplied reasoning supports that change.
- Keep each `rule` atomic and general. Put patient-specific interpretation in `assessment` and `reason`.
- Do not cite, select, rank or mention evidence cards. A separate evidence-matching pass does that.
- Do not create reasoning IDs or internal graph IDs; Python assigns all machine identifiers after this pass.
- Set `supports_conclusion: true` only on the minimal reasoning points that define/support the proposed diagnosis. Phrase such points positively so their assessment is `met`.
- Return exactly one variant assessment for every supplied variant.
- WHO5 `schema_disease` must be populated and `status` must be `established`.
- Keep the reasoning set minimal: include only points needed to justify the diagnosis and important exclusions/refinements.
- Every atomic `reasoning` row must retain all six fields: `rule`, `case_fact_ids`, `variant_ids`, `assessment`, `supports_conclusion`, and `reason`.
- `supports_conclusion: true` is valid only when that same row has `assessment: met`.
- On a feedback redo, change only the object(s) implicated by the deterministic feedback unless correcting that object logically requires a linked field in the same object to change. Preserve all unrelated clinical decisions.

## Feedback from a prior clinical-reasoning attempt
{{ input.audit_feedback }}

## Owner pack
{{ input.owner_pack }}
