---
id: core.report.paraphrase-check
semantic_type: report.paraphrase_semantic_check
format: yaml
provides: [preserved, issue]
requires: []
validator: paraphrase_preservation_check
runtime_invariants: [reject_only]
---
# Paraphrase preservation-check output

Return YAML only:

```yaml
preserved: true
issue: null
```

or, when any source proposition is lost/altered or new clinical content is added:

```yaml
preserved: false
issue: "The paraphrase omits the adverse-risk qualification from source fact F0004."
```
