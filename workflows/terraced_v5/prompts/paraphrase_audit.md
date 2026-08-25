{{ include "includes/audit_general.md" }}

# Final paraphrase preservation audit

For EVERY block, compare the final paraphrased sentence with all source parts in that block.

Set `preserved: false` when the paraphrase materially:
- loses, reverses, strengthens, broadens, or adds a clinical proposition or qualifier;
- adds molecular specificity absent from the source block;
- removes molecular specificity that carries a clinically meaningful distinction;
- substitutes a different molecular identity;
- imports new clinical content from `case.md`.

Do not reject harmless wording or style differences.

Return YAML only, preserving block IDs and order:
```yaml
audits:
  - block_id: diagnosis-1
    preserved: true
    issue: null
    negative_guidance: []
```
