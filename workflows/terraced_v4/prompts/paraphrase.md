# Batched block paraphrasing

For EVERY supplied block, write exactly ONE concise, clinically readable, self-contained report sentence.

Preserve ALL semantic information contained in every source part within that block. Preserve disease/gene scope, polarity, uncertainty, thresholds, classification basis and authoritative qualifiers. Do not add any proposition from another block. Do not add citations.

Return YAML only, preserving block IDs and order:
```yaml
sentences:
  - block_id: diagnosis-1
    sentence: "One self-contained sentence preserving every source proposition in this block."
```
