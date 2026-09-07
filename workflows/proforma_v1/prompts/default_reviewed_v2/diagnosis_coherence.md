# Diagnosis coherence audit

Decide, for each supplied diagnostic assessment, whether the stated conclusion follows from the reasons the clinical owner actually gave.

You are not auditing literature support. No corpus and no evidence cards are supplied to this step, and you must not introduce any. Every reason may be individually true and correctly cited and the assessment can still fail this audit.

## What to check

For each review, the `conclusion` and the `stated_reasons` are supplied as separate fields. Read them against each other and against `patient_findings`.

Fail the review when:

- a stated reason asserts that a defining requirement of the conclusion is absent, and the conclusion nevertheless asserts it;
- the stated reasons, taken together, establish a different entity from the one named in the conclusion;
- a stated reason directly contradicts another stated reason;
- the conclusion depends on a patient finding that the supplied findings contradict or do not establish;
- a stated reason explicitly denies the conclusion it is offered in support of.

Worked example of a failure:

```text
conclusion: MDS with mutated TP53
stated_reasons:
  - one TP53 variant identified
  - no del(17p) or other TP53 copy loss
  - therefore not MDS with mutated TP53
```

Every reason here is individually true. The derivation establishes a monoallelic state and then explicitly denies the conclusion, so the assessment is incoherent regardless of citation quality. Report it, and do not repair it silently in your own reading.

Do not fail a review merely because you would have reached a different medical conclusion. A conclusion you disagree with, but which follows from its own stated reasons and the supplied findings, is a `pass` at this step.

## Choosing a scope

When `status` is `revision_required` you must also state `scope`:

- `reason` — the conclusion is right and the stated derivation is what needs correcting.
- `conclusion` — the stated reasons are right and the named conclusion is what is wrong.

`conclusion` findings are surfaced for human attention and are deliberately not applied automatically. Use it when the label itself is the defect.

`deterministic_flags` is a cheap text-level prior computed by the workflow. It is a hint only. An empty list does not mean the assessments are coherent, and a flag does not by itself mean they are not.

## Output

Return exactly one YAML mapping, with exactly one review for every supplied `authority`, using the supplied authority values unchanged:

```yaml
reviews:
  - authority: who1
    status: revision_required
    scope: reason
    issues:
      - The stated reasons establish monoallelic TP53 and then deny the named entity.
  - authority: icc
    status: pass
    issues: []
```

Omit `scope` when `status` is `pass`. State issues in plain clinical English; do not emit identifiers, field paths, or references to workflow internals.

Assessments to review:
{{ input.coherence_packet }}
