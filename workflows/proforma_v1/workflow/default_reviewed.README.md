# `default_reviewed` reasoning layer

`default_reviewed.yaml` retains the default proforma clinical/evidence/reporting machinery but adds explicit reasoning boundaries around the reviewed clinical owners.

The reviewed path is:

```text
clinical owner (CEO)
→ Secretary
→ Reasoning-1
→ existing evidence assignment/audit/adjudication
→ Reasoning-2 only if final evidence removes a contributing premise
→ deterministic reasoning trace
→ existing report pipeline
```

Responsibilities are intentionally narrow:

- **Clinical owner:** makes the medical decision in the familiar phase-specific proforma. It does not emit card-tag bookkeeping for PTBG.
- **Secretary:** source-links and atomizes the owner's stated reasons. Python owns fact IDs and conclusion dependencies. The Secretary may not add or reinterpret medicine.
- **Reasoning-1:** checks Secretary fidelity and whether the conclusion follows from the owner's own stated premises. It has no corpus or disease/framework rules.
- **Evidence:** the existing match/audit/adjudication machinery remains authoritative for literature support.
- **Reasoning-2:** runs only for affected conclusions after an evidence-required contributing premise is actually lost. `survives_with_qualification` and `revise` return to the affected clinical owner in this minimal pass.

`reasoning-trace.md` is rendered deterministically from these explicit artifacts. It is an audit trail, not model chain-of-thought.

## Deliberate limits of this pass

This is not a general clinical knowledge graph. Dependencies are only conclusion → contributing facts plus the original synthesis. Evidence resolution still operates on the existing reportable proforma propositions rather than on every Secretary atom. Generic reasoning therefore detects internal contradiction/coherence, not a medically wrong but internally coherent premise.
