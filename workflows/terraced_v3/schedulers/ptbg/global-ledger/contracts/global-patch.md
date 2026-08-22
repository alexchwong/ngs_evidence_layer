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
  - domain: "<domain requiring replacement>"
    reason: "<why the original domain state needs replacement>"
    replacement: "<complete canonical replacement state for that domain>"
```

Angle-bracketed text describes the required content only. It is not a preferred review outcome and must never be copied as the adjudication.

Return `changes: []` when no domain requires replacement. A replacement is a complete canonical state for that domain.

Within a replacement domain, preserve every still-correct surfaced `fact`, its `case_refs`, and its `card_tags` exactly. A changed fact text or changed card attribution is treated by core as a new reportable fact.
