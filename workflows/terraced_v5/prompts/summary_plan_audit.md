{{ include "includes/audit_general.md" }}

# Summary-plan audit

Audit the omit/split/merge plan against the ORIGINAL atomic reportable statements and deterministically assembled blocks.

Check:
- `preserved`: no material proposition, qualifier, classification basis, polarity, uncertainty, or context is lost/changed/added.
- `unnecessarily_fragmented`: multiple same-category blocks could clearly be combined into fewer clinically readable sentences without semantic loss.

Do not reject harmless reordering, grouping, or true redundancy removal. When a problem is found, identify the affected statement/block and give negative guidance rather than replacement prose.

Return YAML only:
```yaml
preserved: true
unnecessarily_fragmented: false
issues: []
```
