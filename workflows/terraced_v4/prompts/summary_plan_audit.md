# Summary-plan semantic-preservation audit

Audit the proposed omit/split/merge plan against the ORIGINAL reportable sentences and the deterministically assembled blocks.

Set `preserved: false` if:
- an omitted statement contains material information not safely represented elsewhere;
- a split loses, reverses, overstates or adds a proposition;
- a merge places semantically incompatible material in one block;
- qualifying facts explaining WHY a diagnosis/classification applies are lost.

Do not reject harmless reordering, grouping, or true redundancy removal.

When `preserved: false`, give specific actionable issues naming the affected statement ID or block ID.

Return YAML only:
```yaml
preserved: true
issues: []
```
