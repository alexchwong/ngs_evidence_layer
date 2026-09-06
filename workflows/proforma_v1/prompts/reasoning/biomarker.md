# Biomarker / MRD — clinical reasoning

Reason only about MRD/biomarker suitability in the authoritative disease. Do not match evidence cards and do not construct internal graph IDs.

Return one YAML mapping only:

```yaml
domain: biomarker
variant_assessments:
  - variant_id: V1
    status: <mrd_marker|not_mrd_marker>
    reason: <concise integrated conclusion>
    reasoning:
      - rule: <atomic MRD rule>
        case_fact_ids: []
        variant_ids: [V1]
        assessment: <met|not_met|unknown>
        supports_conclusion: true
        reason: <patient-specific application>
```

Rules:
- Every supplied variant must appear exactly once.
- Classify each as exactly `mrd_marker` or `not_mrd_marker`.
- A positive marker conclusion requires evidence for MRD use in the authoritative disease; prognostic or diagnostic relevance alone is insufficient.
- Do not infer longitudinal persistence, clearance, assay sensitivity or MRD performance that is not supplied.
- Use only supplied patient facts, source-facing variant IDs, authoritative diagnosis and reference material.
- Do not cite or mention evidence cards. Evidence matching is separate.
- Every atomic `reasoning` row must retain all six fields: `rule`, `case_fact_ids`, `variant_ids`, `assessment`, `supports_conclusion`, and `reason`.
- `supports_conclusion: true` is valid only when that same row has `assessment: met`.
- On a feedback redo, change only the object(s) implicated by the deterministic feedback unless correcting that object logically requires a linked field in the same object to change. Preserve unrelated biomarker decisions.

## Feedback from a prior clinical-reasoning attempt
{{ input.audit_feedback }}

## Owner pack
{{ input.owner_pack }}
