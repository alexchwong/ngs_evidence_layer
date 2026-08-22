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
action: keep
reason: "Brief adjudication."
replacement: null
```

Use `action: replace` only when correction is required, with `replacement` containing the complete corrected decision row for the selected cell. The replacement may not change the protected cell scope.
