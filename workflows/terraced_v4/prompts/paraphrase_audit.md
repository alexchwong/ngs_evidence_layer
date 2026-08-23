# Semantic-preservation audit

Compare the paraphrased sentence with the planned draft and source statements. Return `preserved: true` unless the paraphrase materially loses, reverses, overstates or adds a clinical proposition. Do not reject harmless wording/style differences.

Return YAML only:
```yaml
preserved: true
issue: null
```
