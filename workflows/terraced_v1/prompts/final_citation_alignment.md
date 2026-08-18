# Final sentence-to-fact citation alignment

Semantically match every indexed report sentence to one or more accepted facts in the same clinical domain.

Return only this YAML structure:

```yaml
alignments:
  - sentence_id: diagnosis-1
    fact_ids: [diagnosis-1]
  - sentence_id: diagnosis-2
    fact_ids: [diagnosis-2, diagnosis-3]
```

Rules:
- include every supplied `sentence_id` exactly once and preserve their supplied order;
- use only supplied `fact_id` values from the same domain as the sentence;
- list every accepted fact represented by the sentence, without duplicates;
- do not copy report prose, facts, reasons, citations or runtime card tags into the output;
- do not search for new evidence and do not create numeric citations or a bibliography;
- if every sentence cannot be reasonably matched, return `unmatched_sentences` instead of `alignments`, with every unmatched sentence's supplied ID, exact supplied text, and a concise actionable reason:

```yaml
unmatched_sentences:
  - sentence_id: germline-1
    sentence: "No germline predisposition is identified."
    reason: "The accepted fact says only that no germline-predisposition fact is reportable; the sentence strengthens this into a negative finding."
```

- unmatched reasons must identify the unsupported or materially altered wording and explain how it differs from the supplied accepted facts; do not propose outside evidence or replacement clinical facts.

Citation dispositions and final prose are assembled deterministically from this mapping. Your only task is sentence-to-fact semantic alignment.
