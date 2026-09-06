# PTBG patient-applicability and conclusion-coherence audit

Return exactly one YAML mapping conforming to the declared schema. YAML only.

```yaml
derived_states: []
criteria:
  - criterion_id: <exact supplied application_id>
    status: <met|not_met|unknown>
    case_fact_ids: []
    comments: []
conclusions:
  - conclusion_id: <exact supplied proposition/conclusion ID>
    status: <coherent|incoherent|indeterminate>
    comments: []
```

Assess every supplied application and every final clinical conclusion using only evidence-approved rules and supplied patient facts.
- Conclusion coherence is mandatory in prognosis, treatment, biomarker and germline.
- Prognosis: framework applicability/tier and non-framework evidence must remain distinct; a cohort association cannot substitute for an IPSS-M tier.
- Treatment: target/sensitivity/resistance category and named therapy must follow the reasoning.
- Biomarker: MRD marker/not-marker must follow MRD-specific reasoning.
- Germline: the final bucket must follow the integrated factor worksheet; discordant factors must genuinely weigh against `germline_suspicious`.
- Do not search for literature or change rules.
- If a conclusion is incoherent, explain the contradiction for targeted owner revision.

## Deterministic feedback from a prior invalid reasoning artifact
{{ input.audit_feedback }}

## Reasoning items
{{ input.reasoning_items }}
