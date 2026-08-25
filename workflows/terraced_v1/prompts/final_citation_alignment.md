# Final sentence-to-fact citation alignment

Semantically match every indexed report sentence to one or more retained accepted facts in the same clinical domain.

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
- list every retained fact represented by the sentence, without duplicates;
- the complete alignment must cover every supplied retained `fact_id` at least once; multiple facts may map to one sentence;
- do not copy report prose, facts, reasons, citations or runtime card tags into the output;
- do not search for new evidence and do not create numeric citations or a bibliography;
- if a report sentence cannot be reasonably matched, return `unmatched_sentences` instead of `alignments`, with every unmatched sentence's supplied ID, exact supplied text, and a concise actionable reason:

```yaml
unmatched_sentences:
  - sentence_id: germline-1
    sentence: "No germline predisposition is identified."
    reason: "The retained fact does not support this stronger negative conclusion."
```

If the report simply omitted a retained fact, return the best truthful `alignments` for the sentences that exist. Deterministic validation will detect uncovered retained facts and send them back to the synthesis model; do not falsely attach an omitted fact to an unrelated sentence merely to force coverage.

Citation dispositions and final prose are assembled deterministically from this mapping. Your only task is sentence-to-fact semantic alignment.
