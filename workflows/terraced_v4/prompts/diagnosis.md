# Terraced-v4 diagnosis proforma

Complete the whole diagnosis proforma. Use the supplied case and diagnostic evidence only.

Compulsory questions:
1. What is the WHO 5th Edition diagnosis? Return concurrent WHO5 diagnoses separately if present.
2. What is the ICC diagnosis? Return concurrent ICC diagnoses separately if present.
3. Are WHO5 and ICC concordant? If not, state the clinically meaningful difference.
4. Which case facts contradict or are inadequately explained by the primary diagnosis and support a concurrent second diagnosis? If a concurrent diagnosis is explicitly declared in the stem, state it and explain its supporting case facts.

For every diagnosis/concordance answer, provide one or more granular reasons. Each reason should be one independently understandable proposition. Patient facts may be used as premises. Do not choose citations in this pass.

Use only an exact supplied WHO5 `schema_disease` value. Do not write CMC values; core derives CMCs deterministically from WHO5 schema disease.

Return YAML only:
```yaml
who5:
  diagnoses:
    - schema_disease: "<allowed schema disease>"
      status: "established | indeterminate"
      diagnosis: "<WHO5 diagnostic label>"
      reasons:
        - "<granular reason>"
icc:
  diagnoses:
    - status: "established | indeterminate"
      diagnosis: "<ICC diagnostic label>"
      reasons:
        - "<granular reason>"
concordance:
  answer: "<concordant or clinically meaningful difference>"
  reasons:
    - "<reason>"
concurrent_second_diagnosis:
  answer: "<supported diagnosis, none supported, or uncertain>"
  reasons:
    - "<reason>"
```
