# One-pass final block paraphrasing

For EVERY supplied deterministic report block, write exactly ONE concise, clinically readable, self-contained report sentence.

Preserve every semantic proposition in the block: disease/gene scope, polarity, uncertainty, thresholds, classification basis, named framework, treatment context, and conditional qualifiers.

The supplied `case.md` is CONTEXT ONLY. It may help patient-specific wording but must not introduce any clinical proposition that is absent from the source block. Do not move information between blocks. Do not add citations.

Return YAML only, preserving block IDs and order:
```yaml
sentences:
  - block_id: diagnosis-1
    sentence: "One sentence preserving every source proposition in this block."
```
