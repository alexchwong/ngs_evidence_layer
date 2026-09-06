# Prognosis — clinical reasoning

Reason only about prognosis. Do not match evidence cards and do not construct internal graph IDs.

The accepted framework preset is authoritative:
- AML: ELN 2022 genetic risk classification
- AML treated with less-intensive therapy: ELN 2024 less-intensive genetic risk classification
- MDS: IPSS-M
- CMML: CPSS-Mol
- Primary myelofibrosis: MIPSS70; MIPSS70-plus; MIPSS70+ v2.0
- Post-PV/post-ET myelofibrosis: MYSEC-PM
- Essential thrombocythaemia: MIPSS-ET
- Polycythaemia vera: MIPSS-PV
- Essential thrombocythaemia thrombosis risk: revised IPSET-thrombosis
- CHIP/CCUS: CHRS

Return one YAML mapping only:

```yaml
domain: prognosis
frameworks:
  - name: <exact preset framework name>
    applicable: true
    tier: null
    reason: <why the framework applies; if tier is populated, why that tier is established>
    reasoning:
      - rule: <atomic framework rule>
        case_fact_ids: []
        variant_ids: []
        assessment: <met|not_met|unknown>
        supports_conclusion: true
        reason: <patient-specific application>
variant_assessments:
  - variant_id: V1
    framework_effects: []
    other_evidence:
      effect: <favorable|adverse|neutral|no_evidence>
      reason: null
      reasoning: []
```

Rules:
- First identify every preset framework that genuinely applies to the authoritative disease. Framework assessment is patient-level and independent of whether NGS variants were detected.
- If the authoritative disease is MDS, the framework name is exactly `IPSS-M`. Do not rename it to `MDS`, a study/cohort, or a variant-specific association on either the initial answer or a feedback redo.
- Populate a framework tier only when it can be assigned from the supplied findings permitted by that framework. Otherwise use `tier: null`; framework applicability still remains.
- Keep framework-derived effects separate from `other_evidence`. A non-framework adverse association must not be presented as a framework risk tier.
- Every supplied variant must appear exactly once in `variant_assessments`, even when it has no prognostic effect.
- When there are no supplied NGS variants, `variant_assessments: []` but disease-level framework assessment still occurs.
- If the authoritative disease is `no_haematological_malignancy`, return `frameworks: []`.
- Use only supplied patient facts, source-facing variant IDs, authoritative diagnosis and supplied reference material.
- Do not cite or mention evidence cards. Evidence matching is separate.
- Keep each `rule` atomic and general; patient application belongs in `assessment` and `reason`.
- Every atomic `reasoning` row anywhere in the artifact must retain all six fields: `rule`, `case_fact_ids`, `variant_ids`, `assessment`, `supports_conclusion`, and `reason`.
- `supports_conclusion: true` is valid only when that same row has `assessment: met` and genuinely supports the stated framework/effect conclusion.
- On a feedback redo, repair the reported object(s) only. Preserve framework names, variant effects, reasons and all unrelated reasoning rows unless the deterministic defect requires a change within that same object.

## Feedback from a prior clinical-reasoning attempt
{{ input.audit_feedback }}

## Owner pack
{{ input.owner_pack }}
