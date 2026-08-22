# Terraced-v3 case structuring

Convert the authoritative case stem into immutable structured state. Do not diagnose the case.

Return JSON only with exactly this shape:

```json
{
  "provisional_disease": "verbatim/faithful short clinicopathological provisional disease description",
  "bootstrap_cmcs": ["one or more allowed case-major categories"],
  "variants": [
    {"variant_id": "V1", "gene": "GENE", "description": "complete reported variant description"}
  ],
  "detected_variants_summary": "NGS detected GENE NM_...:c...., p.(...), VAF ...%.",
  "case_facts": [
    {"fact_id": "C1", "kind": "short source kind", "value": "one case fact"}
  ]
}
```

Rules:
- preserve every explicitly reported NGS variant exactly once, in case order; assign sequential IDs V1, V2, ...;
- `gene` is the uppercase reported gene symbol and `description` preserves transcript/coding HGVS/protein HGVS/VAF details when supplied;
- `detected_variants_summary` is mandatory and contains exactly one source-faithful sentence listing every detected NGS variant in case order, including gene, supplied HGVS nomenclature and supplied VAF. It is an invariant report sentence: do not interpret the variants. If HGVS or VAF was not supplied for a variant, do not invent it; preserve the supplied nomenclature instead;
- case facts are observations from the stem, not literature interpretation or new diagnosis;
- assign sequential case fact IDs C1, C2, ...;
- `bootstrap_cmcs` is retrieval scaffolding only. Base it on the supplied clinicopathological/provisional disease family, not on what a molecular finding might imply diagnostically;
- do not use NGS findings to upgrade or change the bootstrap disease family;
- use only exact supplied allowed CMC values;
- do not add commentary or Markdown.
