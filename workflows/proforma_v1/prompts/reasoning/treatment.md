# Treatment — clinical reasoning

Reason only about treatment implications in the authoritative disease. Do not match evidence cards and do not construct internal graph IDs.

Return one YAML mapping only:

```yaml
domain: treatment
variant_assessments:
  - variant_id: V1
    implications:
      - category: <drug_target|drug_sensitive|drug_resistant|no_drug_implication>
        therapy: <named therapy or null>
        reason: <concise integrated conclusion>
        reasoning:
          - rule: <atomic treatment rule>
            case_fact_ids: []
            variant_ids: [V1]
            assessment: <met|not_met|unknown>
            supports_conclusion: true
            reason: <patient-specific application>
```

Rules:
- Every supplied variant must appear in `variant_assessments`.
- Positive implications use only `drug_target`, `drug_sensitive`, or `drug_resistant` and must name the therapy.
- `drug_target` means the lesion itself is directly targetable; do not use it for mere response association.
- `no_drug_implication` uses `therapy: null` and is mutually exclusive with positive implications for that variant.
- Multiple rows are allowed only for genuinely distinct treatment implications.
- Every positive treatment conclusion must apply to the authoritative disease; do not borrow another-disease evidence merely because the gene is shared.
- Use only supplied patient facts, source-facing variant IDs, authoritative diagnosis and reference material.
- Do not cite or mention evidence cards. Evidence matching is separate.
- Keep reasoning atomic and minimal.

## Feedback from a prior clinical-reasoning attempt
{{ input.audit_feedback }}

## Owner pack
{{ input.owner_pack }}
