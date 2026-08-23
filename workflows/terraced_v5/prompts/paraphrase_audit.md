{{ include "includes/audit_general.md" }}

# Final paraphrase preservation audit

For EVERY block, compare the final paraphrased sentence with all source parts in that block.

Set `preserved: false` only when the paraphrase materially loses, reverses, strengthens, broadens, or adds a clinical proposition or qualifier. Reject new clinical content imported from `case.md`. Do not reject harmless wording/style differences.

Return YAML only, preserving block IDs and order:
```yaml
audits:
  - block_id: diagnosis-1
    preserved: true
    issue: null
    negative_guidance: []
```
