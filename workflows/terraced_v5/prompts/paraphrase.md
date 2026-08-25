# One-pass final block paraphrasing

For EVERY supplied deterministic report block, write exactly ONE concise, clinically readable, self-contained report sentence.

Preserve every semantic proposition in the block:
- disease and molecular scope;
- polarity and uncertainty;
- thresholds and classification basis;
- named framework and treatment context;
- conditional qualifiers.

Preserve molecular naming specificity from the source block:
- do not add transcript, HGVS, allele, subtype, or other molecular detail absent from the block;
- do not remove molecular detail when it carries a clinically meaningful distinction;
- do not substitute a different molecular identity.

The supplied `case.md` is CONTEXT ONLY. It may help patient-specific wording but must not introduce any clinical proposition that is absent from the source block. Do not move information between blocks. Do not add citations.

Return YAML only, preserving block IDs and order:
```yaml
sentences:
  - block_id: diagnosis-1
    sentence: "One sentence preserving every source proposition in this block."
```
