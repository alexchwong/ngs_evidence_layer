# Terraced-v1 case structuring

Convert the supplied case into one JSON object. Preserve patient facts; do not clinically interpret the NGS result beyond choosing broad provisional retrieval categories.

Output exactly these top-level fields:

```json
{
  "provisional_cmcs": ["AML"],
  "provisional_disease": "supplied clinicopathological diagnostic wording",
  "genes": ["GENE1", "GENE2"],
  "case_facts": [
    {"fact_id": "F1", "kind": "...", "value": "..."}
  ]
}
```

Rules:
- `provisional_cmcs` is a non-empty list of exact values from `case-major-categories.json`.
- It is based on the starting clinicopathological presentation, before NGS-driven reclassification.
- Use more than one provisional CMC only when the supplied case itself already supports more than one broad disease family; later diagnostic terraces may expand it.
- `provisional_disease` preserves the supplied diagnostic wording without forcing it into the controlled disease vocabulary.
- `genes` contains each reported NGS gene once, uppercase.
- `case_facts` preserves all material patient-level facts needed for interpretation, including morphology, blast percentage, blood counts, cytogenetics/FISH, treatment context, family history, prior disease and follow-up timing when supplied.
- Do not invent absent tests or negative results.
- Return JSON only.
