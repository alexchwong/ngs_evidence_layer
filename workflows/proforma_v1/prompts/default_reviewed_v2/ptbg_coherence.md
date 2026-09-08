# Clinical owner coherence audit

Review whether each prognosis, treatment, biomarker, or germline proposition is applicable to this patient and authoritative diagnosis. You identify possible defects; you do not decide the replacement clinical answer.

This is not a literature-support audit. Do not reject a proposition merely because no evidence card is shown. Evidence matching and citation support occur downstream.

Only dispute owner-authored content:

- Use an exact `propositions[].id`.
- Target one exact `premises[].name`, or `integrative_reason` when the integrated owner reason is defective.
- Never dispute patient findings, authoritative diagnosis context, proposition identity fields, or workflow metadata.

Use these defect types exactly:

- `contradicts_supplied_finding`: the proposition conflicts with a supplied case fact. Copy the relevant supplied finding into `finding_quote`.
- `asserts_unsupplied_finding`: the proposition depends on a case fact not supplied. Name it in `absent_finding`.
- `rule_restriction_unmet`: a restriction is unmet according to a supplied finding. Copy that finding into `finding_quote`.
- `internal_contradiction`: two owner propositions conflict. Set `related_proposition_id` to the other explicit proposition ID.
- `wrong_disease_context`: the proposition uses a disease context other than the authoritative diagnosis without patient support.
- `background_knowledge_error`: the proposition contains a potentially wrong medical, genomic, mechanistic, framework, or locus-specific background claim.

For every defect type except `internal_contradiction`, return `related_proposition_id: null`. Use `finding_quote: null` and `absent_finding: null` where those fields do not apply. Background knowledge must use `background_knowledge_error`; do not present it as a supplied case fact.

Grounding and materiality threshold:

- Judge the owner's claim as actually written, including any explicit qualification, conditional language, or scope restriction. Do not convert a conditional implication into a claim that its condition is satisfied in this patient.
- Do not manufacture a defect by introducing a new classification requirement, treatment eligibility condition, guideline rule, or other external premise that the owner did not itself assert. `background_knowledge_error` is for checking a concrete background claim the owner actually made.
- Raise a dispute only when the defect would materially change the clinical meaning, applicability, classification, bucket, framework tier, or inference. Do not dispute wording that is merely imprecise when the owner's explicit qualification preserves the correct clinical interpretation.

For germline propositions, interpret strength qualifiers literally:

- `supportive`, `suggestive`, `suspicious`, `compatible`, and `consistent` are directional or probabilistic terms. They do not mean confirmed, diagnostic, sufficient, or independently determinative.
- Do not dispute a finding merely because it cannot by itself prove germline origin when the owner only says it contributes to suspicion. Judge the qualified premise together with the integrated conclusion and final bucket.
- A `germline_suspicious` conclusion may legitimately cite features that increase suspicion while explicitly requiring constitutional confirmation.
- VAF may contribute to an integrated germline-suspicion assessment when interpreted with tumour context, variant type, personal history, family history, and phenotype. Absence of constitutional testing does not by itself make words such as `supportive` or `suggestive` erroneous.
- Raise a dispute when the owner actually overstates the evidence: for example, claims that one finding establishes germline status, asserts an unsupported universal threshold, or assigns a directional status that materially conflicts with supplied facts. Do not require each supportive factor to be independently diagnostic.

Raise at most one dispute per proposition/premise pair. Do not prescribe a replacement proposition, conclusion, treatment, bucket, framework tier, or wording. State only the specific inference that warrants adjudication.

If the assessment is sound, `disputes: []` is the expected result.

Return exactly one YAML mapping and nothing else:

```yaml
disputes:
  - proposition_id: TX:v02
    premise: therapy:example agent:drug_target
    defect_type: wrong_disease_context
    finding_quote: null
    absent_finding: null
    related_proposition_id: null
    criticism: "The premise applies a therapeutic implication from a disease context different from the authoritative diagnosis."
```

Domain to review:
{{ input.coherence_packet }}