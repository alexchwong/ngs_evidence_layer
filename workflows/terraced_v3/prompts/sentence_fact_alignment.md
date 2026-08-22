# Final sentence-to-fact semantic alignment

Semantically match every indexed report sentence to one or more supplied locked facts in the same clinical domain.

Return YAML only:

```yaml
alignments:
  - sentence_id: diagnosis-1
    fact_ids: [who5-DX1]
```

Rules:
- include every supplied sentence_id exactly once and preserve order;
- use only supplied fact_id values from the same domain;
- list every fact represented by the sentence, without duplicates;
- do not falsely attach an omitted fact to an unrelated sentence merely to force coverage;
- do not copy prose, reasons, citations or card tags into the output;
- do not create new clinical content.
