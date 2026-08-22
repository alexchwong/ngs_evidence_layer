---
id: summarization.common.paraphrase-output
semantic_type: report.paraphrased_sentence
format: yaml
provides: [sentence_id, sentence]
requires: []
validator: paraphrase_sentence
runtime_invariants: [sentence_id_preserved, semantic_preservation_checked]
---
# One paraphrased sentence

Return YAML only:

```yaml
sentence_id: prognosis-1
sentence: "One self-contained report sentence."
```

Copy the supplied `sentence_id` exactly. Do not return citations or provenance fields.
