# Generic pre-evidence reasoning check

Audit the supplied clinical argument without using medical knowledge, framework knowledge, a corpus, or evidence cards. No corpus or evidence-card content is available to this reasoning step. You are checking representation fidelity and internal reasoning only.

## Representation fidelity
Check that the Secretary faithfully represents the supplied owner source fragments:
- every material source fragment is represented;
- no atom adds, removes, strengthens, weakens, reverses, or resolves clinical meaning;
- negation, uncertainty, scope, attribution, and patient-vs-general-rule distinctions are preserved;
- `evidence_class` is faithful. A general/framework/source-dependent claim must not be mislabeled in a way that bypasses literature evidence.

## Internal coherence
Check whether each stated clinical conclusion is compatible with, and follows from, the premises and synthesis actually supplied by the clinical owner.

This check is generic. Do not decide whether a medical premise is true. A medically wrong rule can still be internally coherent. Fail only when the owner's own statements conflict or do not support the stated conclusion—for example, when an artifact states that a defining requirement is absent and nevertheless concludes that the requirement is satisfied.

Return exactly one YAML mapping:

```yaml
representation:
  status: <faithful|not_faithful>
  comments: []
coherence:
  status: <coherent|incoherent|indeterminate>
  comments: []
```

Clinical owner packet:
{{ input.owner_packet }}

Compiled atomic representation:
{{ input.compiled_reasoning }}

Reasoning-1 artifact feedback from a prior attempt (null on first pass):
{{ input.precheck_feedback }}

If feedback is supplied, repair only the stated structured-output defect. Do not change the clinical owner packet or invent new premises.
