---
id: ptbg.global-ledger.global-patch
semantic_type: ptbg.global.patch
format: yaml
provides: ["changes[].domain", "changes[].reason", "changes[].replacement"]
requires: []
validator: global_patch
runtime_invariants: [replacement_must_validate_as_domain]
---
# Global-ledger review patch output

```yaml
changes:
  - domain: prognosis
    reason: "Why the original domain state needs replacement."
    replacement:
      decisions: []
```

Return `changes: []` when no domain requires replacement. A replacement is a complete canonical state for that domain.
