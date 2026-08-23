# Report sentence combination plan

For every supplied reportable sentence, choose include or omit, then decide final sentence order and which same-domain sentences can safely be combined. Every omission requires a concise reason. Diagnostic classification sentences must be included. Do not reason about citations.

When combining sentences, preserve EVERY material clinical proposition from every `source_statement_id`. This includes qualifying facts that explain why a diagnosis/classification applies, not just the final label. Compress wording, not meaning. If material propositions cannot be safely combined, keep them as separate planned sentences.

Return YAML only:
```yaml
dispositions:
  - statement_id: S0001
    decision: include
    reason: null
sentences:
  - sentence_id: diagnosis-1
    domain: diagnosis
    source_statement_ids: [S0001]
    draft_sentence: "A complete self-contained sentence."
```
