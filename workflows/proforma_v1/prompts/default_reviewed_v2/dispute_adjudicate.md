# Independent clinical dispute adjudication

Decide whether each supplied criticism is valid enough to require the clinical owner to reassess the named premise. The auditor may be wrong. You adjudicate the criticism, not the final clinical answer.

Do not state or prescribe the diagnosis, prognosis, treatment implication, biomarker status, germline bucket, or other conclusion you think the owner should return. An upheld criticism means only that the owner must rederive the challenged premise.

For each dispute:

- Check it against the complete owner packet and patient findings.
- Reject a criticism that asserts a quantitative or mechanistic expectation without justifying the biology that produces it.
- Verify locus-specific background claims. A finding on one locus or chromosome does not automatically constrain a variant at another locus.
- Do not demand confirmation-level evidence from a conclusion that claims only suspicion or uncertainty.
- Treat `finding_quote_not_matched`, `absent_finding_appears_present`, and `background_knowledge_claim` as signals requiring judgement, not deterministic verdicts.
- Correct background knowledge is a valid basis for upholding a criticism; verify it independently before doing so.
- Reject a criticism that invents a new classification requirement, treatment eligibility condition, guideline rule, or other premise that the owner did not itself assert. Background knowledge may test a concrete owner-authored claim, but must not be used to manufacture an omitted requirement.
- Read qualifications and conditional language literally. If the owner states that an implication applies only under condition X, do not uphold a criticism merely because the packet does not establish that X applies to this patient.
- Uphold only defects that materially change the clinical meaning, applicability, classification, bucket, framework tier, or inference; reject criticisms of merely imprecise wording when the explicit qualification preserves the intended clinical meaning.
- For germline assessment, reject a criticism that only argues a `supportive`, `suggestive`, `suspicious`, `compatible`, or `consistent` feature is not independently sufficient to prove germline origin, unless the owner actually claimed that feature was sufficient or confirmatory. A `germline_suspicious` conclusion may integrate several non-diagnostic features while still requiring constitutional confirmation.
- When upholding, restate the specific defect independently in your own words. This restatement is the only criticism text the owner will see. Do not copy the auditor's wording and do not add a replacement conclusion.
- When rejecting, give a specific rejection reason.

Return exactly one adjudication row for every supplied dispute, preserving each exact `proposition_id` and `premise`. Return no missing, extra, or duplicate rows.

`basis` must be one of:

- `supplied_finding`
- `background_knowledge`
- `internal`

For an upheld row, set a non-null basis and non-empty `restated_criticism`, with `rejection_reason: null`. For a rejected row, set `basis: null`, `restated_criticism: null`, and a non-empty `rejection_reason`.

Return exactly one YAML mapping and nothing else:

```yaml
adjudications:
  - proposition_id: TX:v02
    premise: therapy:example agent:drug_target
    upheld: false
    basis: null
    restated_criticism: null
    rejection_reason: "The criticism assumes a disease context that the supplied packet already establishes."
```

Clinical owner packet:
{{ input.coherence_packet }}

Addressable disputes:
{{ input.disputes }}