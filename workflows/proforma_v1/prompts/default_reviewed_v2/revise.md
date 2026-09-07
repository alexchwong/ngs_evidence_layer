# Targeted clinical revision

Correct only the statements supplied below. Each target is one clinical unit that a coherence audit found defective, together with the finding.

You own the wording of the replacement reason and nothing else. Do not restate, regenerate, or comment on any other part of the assessment: unaffected content is preserved by the workflow and is not supplied to you.

## What to return

For each target, return its `index` exactly as supplied and a replacement `reason`.

- **Rescope** when part of the statement is sound: rewrite the reason so that it asserts only what the patient's findings and the accepted evidence actually support. Keep the surviving clinical meaning intact; narrow the claim rather than deleting it.
- **Remove** when nothing survives: return `reason: null`. The workflow then clears the associated evidence-card tags, because the proposition they supported no longer exists.

Do not broaden a claim. Do not introduce a new mechanism, framework, threshold, allelic state, or disease subtype that the supplied material does not already contain. Do not cite literature; no corpus is supplied to this step.

A diagnosis target's reason may be corrected but never removed. If you believe a diagnosis conclusion itself is wrong, that finding was already recorded at the coherence step and is not yours to apply here — correct the stated derivation only.

## Output

Return exactly one YAML mapping, one entry per supplied target:

```yaml
revisions:
  - index: 0
    reason: A single TP53 variant without copy loss indicates a monoallelic state.
  - index: 1
    reason: null
```

Targets:
{{ input.revision_targets }}
