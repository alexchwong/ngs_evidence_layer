---
id: core.case.structured
semantic_type: case.structured
format: json
provides:
  - provisional_disease
  - bootstrap_cmcs[]
  - variants[].variant_id
  - variants[].gene
  - variants[].description
  - detected_variants_summary
  - case_facts[].fact_id
  - case_facts[].kind
  - case_facts[].value
requires: []
validator: validate_case_text
runtime_invariants:
  - stable_variant_ids
  - source_faithful_variant_summary
  - allowed_bootstrap_cmcs
---
# Structured case output

Convert the case into immutable structured state. Do not diagnose the case.

Return JSON only with this shape:

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

Requirements:
- preserve every explicitly reported NGS variant exactly once, in case order; assign `V1`, `V2`, ...;
- preserve transcript/coding HGVS/protein HGVS/VAF details when supplied;
- `detected_variants_summary` is one source-faithful, non-interpretive sentence listing every detected NGS variant;
- case facts are observations from the stem, not literature interpretation;
- `bootstrap_cmcs` is retrieval scaffolding only and must not be upgraded by molecular findings.
