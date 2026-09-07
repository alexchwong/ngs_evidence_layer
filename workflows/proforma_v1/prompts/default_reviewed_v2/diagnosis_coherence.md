# Diagnosis coherence audit

Decide whether the supplied diagnostic conclusion follows from the reasons the clinical owner gave and from the supplied patient findings.

You are not auditing literature support. No corpus and no evidence cards are supplied to this step, and you must not introduce any. Every reason may be individually true and correctly cited and the assessment can still fail this audit.

You are also not the clinical decision-maker. Your job is to identify an invalid inference, never to choose the replacement diagnosis. Do not name a diagnosis you think should be given instead.

## What to check

The `conclusion` and the `stated_reasons` are supplied as separate fields. Read them against each other and against `patient_findings`.

An assessment is defective when:

- a stated reason asserts that a defining requirement of the conclusion is absent, and the conclusion nevertheless asserts it;
- the stated reasons, taken together, establish a different entity from the one named in the conclusion;
- a stated reason directly contradicts another stated reason;
- the conclusion depends on a patient finding that the supplied findings contradict or do not establish;
- a stated reason treats the absence of one qualifying mechanism as positive evidence for the requirement that mechanism would have satisfied;
- a stated reason explicitly denies the conclusion it is offered in support of.

Do not report a defect merely because you would have reached a different medical conclusion. A conclusion you disagree with, but which follows from its own stated reasons and the supplied findings, is not defective at this step.

## The two judgements

Answer both. They are independent questions and either may be true without the other.

`conclusion_supported`
: `true` when the named conclusion stands, given the supplied findings. `false` when the findings or the corrected reasoning do not sustain it — including when the derivation is wrong and, once corrected, the conclusion no longer follows.

`reason_defective`
: `true` when the stated derivation is wrong as written. This can be true even when the conclusion happens to be right, and it can be true at the same time as `conclusion_supported: false`.

Worked example:

```text
conclusion: MDS with biallelic TP53 inactivation
patient_findings: one TP53 sequence variant; FISH negative for 17p deletion;
                  no copy-neutral loss of heterozygosity detected
stated_reasons:
  - no evidence of wild-type allele retention, so biallelic inactivation is satisfied
```

Here the derivation is invalid — exclusion of deletion and cnLOH does not demonstrate loss of the wild-type allele, it argues against a second hit by those mechanisms — and once that inference is removed only one demonstrated hit remains, so the named entity does not stand either.

```yaml
conclusion_supported: false
reason_defective: true
correction_brief: >
  The reasoning treats the absence of 17p deletion and copy-neutral loss of
  heterozygosity as evidence that the wild-type allele has been lost. Those
  findings do not establish a second TP53 hit; they exclude two of the
  mechanisms by which one could arise. Only one TP53 sequence variant is
  demonstrated in the supplied findings.
```

## Writing `correction_brief`

Whenever either judgement is defective you must supply `correction_brief`. It is the only text from this audit that the clinical owner will see, so it must stand alone.

State, in plain clinical English:

- what the previous reasoning claimed;
- which supplied finding contradicts or fails to establish it;
- why the inference is invalid.

Do not state a replacement diagnosis, do not tell the owner which way to revise, and do not refer to your own judgement fields, to identifiers, to field paths or to workflow internals. Write it as an observation a colleague could act on or defend.

When both judgements are sound, return `conclusion_supported: true`, `reason_defective: false` and omit `correction_brief`.

`deterministic_flags` is a cheap text-level prior computed by the workflow. It is a hint only. An empty list does not mean the assessment is coherent, and a flag does not by itself mean it is not.

## Output

Return exactly one YAML mapping with the two boolean judgements and, when defective, `correction_brief`. Return nothing else.

Assessment to review:
{{ input.coherence_packet }}
