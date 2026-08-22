---
id: ptbg.adaptive-microtask.cell-review
semantic_type: ptbg.adaptive.cell_review
format: yaml
provides: [action, reason, replacement]
requires: []
validator: adaptive_cell_review
runtime_invariants: [cell_identity_preserved, replacement_must_validate]
---
# Adaptive cell-review output

Return YAML only:

```yaml
action: "<keep or replace>"
reason: "<brief adjudication>"
replacement: "<null when keeping; complete corrected decision row when replacing>"
```

Angle-bracketed text describes the required content only. It is not a preferred review outcome and must never be copied as the adjudication.

Use `action: replace` only when correction is required, with `replacement` containing the complete corrected decision row for the selected cell. The replacement may not change the protected cell scope.

When replacing a cell, preserve the existing `fact` text and `card_tags` exactly if that reportable proposition remains correct. Change either only when the proposition or its evidence provenance truly changes.
