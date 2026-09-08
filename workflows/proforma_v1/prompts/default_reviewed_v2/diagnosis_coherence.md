# Diagnosis coherence audit

Review whether each owner-authored diagnostic proposition follows from its stated reasoning and the supplied patient findings. You identify possible defects; you do not decide the replacement clinical answer.

Only dispute content the owner authored:

- For the primary diagnosis proposition (`DX-WHO:primary` or `DX-ICC:primary`), target `premise: integrative_reason`.
- For a variant proposition, target one of its exact `premises[].name` values or `integrative_reason`.
- Never dispute patient findings, the starting morphologic diagnosis, deterministic flags, identifiers, or workflow metadata.

Use these defect types exactly:

- `contradicts_supplied_finding`: the reasoning conflicts with a supplied case fact. Copy the relevant supplied finding into `finding_quote`.
- `asserts_unsupplied_finding`: the reasoning depends on a case fact not supplied. Name it in `absent_finding`.
- `rule_restriction_unmet`: a restriction is unmet according to a supplied finding. Copy that finding into `finding_quote`.
- `internal_contradiction`: two owner propositions conflict. Set `related_proposition_id` to the other explicit proposition ID.
- `wrong_disease_context`: the reasoning uses the wrong established disease context.
- `background_knowledge_error`: the reasoning contains a potentially wrong medical, genomic, mechanistic, or locus-specific background claim.

For every defect type except `internal_contradiction`, return `related_proposition_id: null`. Use `finding_quote: null` and `absent_finding: null` when those fields do not apply. Background knowledge must be routed as `background_knowledge_error`, not disguised as a supplied finding.

Grounding and materiality threshold:

- Judge the owner's claim as actually written, including any explicit qualification, conditional language, or scope restriction. Do not convert a conditional implication into a claim that its condition is satisfied in this patient.
- Do not manufacture a defect by introducing a new classification requirement, treatment eligibility condition, guideline rule, or other external premise that the owner did not itself assert. `background_knowledge_error` is for checking a concrete background claim the owner actually made.
- Raise a dispute only when the defect would materially change the clinical meaning, applicability, classification, bucket, framework tier, or inference. Do not dispute wording that is merely imprecise when the owner's explicit qualification preserves the correct clinical interpretation.

Raise at most one dispute per proposition/premise pair. Do not prescribe a replacement diagnosis, classification, conclusion, or wording. A criticism should identify the specific inference that warrants adjudication, not tell the owner what answer to return.

If the assessment is sound, `disputes: []` is the expected result.

Return exactly one YAML mapping and nothing else:

```yaml
disputes:
  - proposition_id: DX-WHO:primary
    premise: integrative_reason
    defect_type: contradicts_supplied_finding
    finding_quote: "molecular finding: only one pathogenic variant was detected"
    absent_finding: null
    related_proposition_id: null
    criticism: "The integrative reason treats a single demonstrated event as satisfying a requirement that it describes as needing two events."
```

Assessment to review:
{{ input.coherence_packet }}