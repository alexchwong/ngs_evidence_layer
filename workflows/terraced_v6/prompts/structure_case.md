# Structure the case

Return JSON only using exactly this shape:

```json
{
  "provisional_disease": "short source-faithful provisional disease description",
  "bootstrap_cmcs": ["one or more exact allowed CMC values"],
  "variants": [
    {"variant_id": "V1", "gene": "GENE", "description": "GENE complete reported variant description"}
  ],
  "detected_variants_summary": "One sentence listing every detected NGS variant.",
  "case_facts": [
    {"fact_id": "C1", "kind": "short kind", "value": "source-faithful patient fact"}
  ]
}
```

Use only information explicitly present in the case. Do not infer a diagnosis that the case does not support. `bootstrap_cmcs` are retrieval scaffolds, not diagnoses.

For `variants`:
- preserve every reported NGS variant;
- `gene` is the reported uppercase gene symbol;
- `description` begins with the exact `gene`, followed by the complete reported variant description;
- preserve all supplied transcript, cDNA, protein, VAF, and other variant detail;
- do not simplify `description` for report prose; report abstraction occurs downstream;
- do not infer or add molecular detail absent from the case.
