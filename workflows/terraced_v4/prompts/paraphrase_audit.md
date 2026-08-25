# Batched semantic-preservation audit

For EVERY supplied block, compare the paraphrased output sentence with all source parts in that block.

Return `preserved: true` unless the paraphrase materially loses, reverses, overstates or adds a clinical proposition. Do not reject harmless wording/style differences.

Return YAML only, preserving block IDs and order:
```yaml
audits:
  - block_id: diagnosis-1
    preserved: true
    issue: null
```
