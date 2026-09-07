# Clinical reasoning coherence audit

Decide whether the supplied propositions from one clinical domain follow from their stated reasons, from the supplied patient findings, and from the authoritative diagnosis.

## Scope of this audit

You are **not** auditing literature support. No corpus and no evidence cards are supplied, and you must not introduce any. Whether a proposition is backed by a citable card is settled downstream by a separate evidence chain; a proposition with no supporting card is not your concern and is not a defect at this step.

What you are checking is narrower and is not covered anywhere else: whether the clinical claim is consistent with **this patient** and **this diagnosis**.

You are not the clinical decision-maker. Identify the invalid inference. Never state the prognosis, treatment implication, biomarker or germline conclusion that you think should replace it, and never say which bucket a proposition belongs in.

## What to check

For each supplied proposition, read `statement` and `stated_reason` against `patient_findings` and `authoritative_diagnosis`.

A domain assessment is defective when:

- a proposition asserts a patient feature the supplied findings contradict, or do not establish — for example describing an allelic state, cytogenetic abnormality, blast level or exposure history the case does not show;
- a proposition applies a clinical rule to this patient without the restriction that rule carries, where the supplied findings show the restriction is not met;
- a proposition is stated in a disease context other than the authoritative diagnosis, without the supplied findings establishing that context;
- a stated reason contradicts another proposition in the same domain;
- a stated reason explicitly denies the statement it is offered in support of;
- a framework or scoring system is asserted as applied when the supplied findings lack the inputs that framework requires, and the proposition does not say so.

Do not report a defect merely because you would have weighed the clinical picture differently, because a proposition seems obvious, or because you would have said more. Restating the statement as the reason is common in this workflow and is not by itself a defect: judge the claim against the patient, not against its own phrasing.

Worked example:

```text
authoritative_diagnosis: MDS with low blasts and multilineage dysplasia
patient_findings: one TP53 sequence variant at VAF 12%; normal karyotype;
                  no 17p loss; no copy-neutral loss of heterozygosity
statement: Multi-hit TP53 (biallelic inactivation by mutation plus copy-neutral
           LOH) is associated with inferior overall survival in MDS.
```

The prognostic claim itself is unremarkable, but it is asserted of a patient in whom copy-neutral LOH is explicitly excluded, so the allelic state it depends on is not this patient's.

```yaml
conclusion_supported: false
reason_defective: true
correction_brief: >
  The prognostic claim is stated for multi-hit TP53 arising from a mutation plus
  copy-neutral loss of heterozygosity. The supplied findings record a single TP53
  variant at VAF 12% with copy-neutral loss of heterozygosity explicitly excluded
  and a normal karyotype, so the allelic state the claim depends on is not
  established in this patient.
```

## The two judgements

Answer both for the domain as a whole. They are independent and either may be true without the other.

`conclusion_supported`
: `true` when the domain's propositions stand as clinical claims about this patient under the authoritative diagnosis. `false` when one or more do not — including when a derivation is wrong and, once corrected, the proposition no longer follows.

`reason_defective`
: `true` when a stated reason is wrong as written, independently of whether the proposition it supports happens to stand.

## Writing `correction_brief`

Whenever either judgement is defective you must supply `correction_brief`. It is the only text from this audit the clinical owner will see, so it must stand alone.

State, in plain clinical English: which proposition is affected, what it claimed, which supplied finding or diagnosis contradicts or fails to establish it, and why the inference is invalid. Where more than one proposition is affected, cover each.

Do not prescribe the replacement claim, do not refer to your own judgement fields, and do not emit identifiers, field paths, bucket names or references to workflow internals.

When the domain is sound, return `conclusion_supported: true`, `reason_defective: false` and omit `correction_brief`.

## Output

Return exactly one YAML mapping with the two boolean judgements and, when defective, `correction_brief`. Return nothing else.

Domain to review:
{{ input.coherence_packet }}
