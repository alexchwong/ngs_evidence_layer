# Structure the case

Return JSON only using exactly this shape:

```json
{
  "provisional_disease": "short source-faithful provisional disease description",
  "bootstrap_cmcs": ["one or more exact allowed CMC values"],
  "variants": [
    {"variant_id": "V1", "gene": "GENE", "description": "complete reported variant description"}
  ],
  "detected_variants_summary": "One sentence listing every detected NGS variant.",
  "case_facts": [
    {"fact_id": "C1", "kind": "short kind", "value": "source-faithful patient fact"}
  ]
}
```

Use only information explicitly present in the case. Do not infer a diagnosis that the case does not support. `bootstrap_cmcs` are retrieval scaffolds, not diagnoses.
