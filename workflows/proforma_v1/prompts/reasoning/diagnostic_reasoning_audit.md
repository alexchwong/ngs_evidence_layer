# Diagnostic patient-applicability and conclusion-coherence audit

Return exactly one YAML mapping conforming to the declared schema. YAML only.

```yaml
derived_states: []
criteria:
  - criterion_id: <exact supplied criterion/application ID>
    status: <met|not_met|unknown>
    case_fact_ids: []
    comments: []
conclusions:
  - conclusion_id: <who5|icc|second_diagnosis>
    status: <coherent|incoherent|indeterminate>
    comments: []
```

Use only supplied evidence-approved rules, patient facts/variants and the owner's fixed clinical reasoning.
- Audit every supplied criterion for patient applicability.
- Audit every supplied final owner conclusion for coherence with the owner's own audited reasoning.
- A conclusion is `incoherent` when it contradicts, overstates or understates the reasoning. Example: reasoning excludes a defining subtype but the final diagnosis still names that subtype.
- Do not search for evidence or compare WHO against ICC.
- Do not choose a different diagnosis yourself. If incoherent, explain the contradiction so the originating owner can revise it.

## Deterministic feedback from a prior invalid reasoning-audit result
{{ input.audit_feedback }}

## Audit items
{{ input.reasoning_items }}
