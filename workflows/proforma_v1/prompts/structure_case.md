# Structure the case

Return JSON only using exactly this shape:
```json
{
  "provisional_disease": "short source-faithful provisional morphologic disease description",
  "morphologic_diagnosis_origin": "supplied|inferred",
  "bootstrap_cmcs": ["one or more exact allowed CMC values"],
  "variants": [
    {"variant_id": "V1", "gene": "GENE", "description": "GENE complete reported variant description"}
  ],
  "detected_variants_summary": "One sentence listing every detected NGS variant, or stating that no NGS variants were detected.",
  "ngs_result_completeness": "complete|incomplete",
  "ngs_no_variants_detected": [],
  "case_facts": [
    {"fact_id": "C1", "kind": "short kind", "value": "source-faithful patient fact"}
  ]
}
```
Morphologic diagnosis rules:
- Only an explicit supplied diagnostic label counts as a morphologic/pathologic diagnosis. Copy that label source-faithfully into `provisional_disease` and return `morphologic_diagnosis_origin: supplied`.
- Descriptive marrow or tissue findings are not diagnoses. For example, statements such as normal trilineage hematopoiesis, left-shifted granulopoiesis, dysplasia descriptions, cellularity, blast percentages, or other observations remain `case_facts` unless the case separately supplies an explicit diagnostic label.
- If no morphologic/pathologic diagnosis is explicitly supplied, return `provisional_disease: "No morphologic diagnosis supplied"` and `morphologic_diagnosis_origin: inferred`. Do not invent a provisional disease label from descriptive morphology, cytopenias, other nonspecific laboratory findings, or NGS findings. Molecular refinement occurs downstream.
- `bootstrap_cmcs` are retrieval scaffolds, not diagnoses. When there is no explicit morphologic diagnosis, morphology is explicitly normal or non-diagnostic, no NGS variants are detected, and current cytogenetic/other molecular findings are absent, normal, pending, unavailable, not performed, or otherwise non-diagnostic, use `no_haematological_malignancy` as the bootstrap CMC. This is an internal no-established-diagnosis routing sentinel; it does not assert that a myeloid neoplasm has been excluded.
For `variants`:
- preserve every reported NGS variant;
- when the case explicitly states that no NGS variants were detected, or gives an equivalent unequivocal negative NGS result, return `variants: []` and state that no NGS variants were detected in `detected_variants_summary`;
- never create a pseudo-variant representing "no variants detected" or another negative result;
- `gene` is the reported uppercase gene symbol;
- `description` begins with the exact `gene`, followed by the complete reported variant description;
- preserve all supplied transcript, cDNA, protein, VAF, and other variant detail;
- do not simplify `description` for report prose; report abstraction occurs downstream;
- do not infer or add molecular detail absent from the case.
For NGS result completeness:
- return `ngs_result_completeness: complete` unless the case explicitly describes the supplied NGS result as partial, selected, limited, abbreviated, pending, or otherwise incomplete;
- return `ngs_result_completeness: incomplete` only when such incompleteness is explicit;
- always return `ngs_no_variants_detected: []`; core fills this field deterministically from the configured NGS panel after validating your detected-variant extraction.
For `case_facts`:
- preserve every explicitly supplied patient-level or test-level fact that may affect downstream interpretation;
- this includes, when supplied: demographics, blood counts and other laboratory measurements, morphology/histology, blast percentages, flow/immunophenotype, cytogenetics/karyotype/FISH, copy-number or structural findings, non-NGS molecular tests, treatment/exposure history, prior disease, personal/family history, specimen or assay context, and follow-up/timing information;
- treat labelled case sections such as Blood, Marrow, Morphology, Flow, Cytogenetics, Karyotype, FISH, PCR, and similar laboratory headings as explicit sources of patient facts;
- do not omit a cytogenetic, FISH, copy-number, structural, or other finding because it involves the same gene as an NGS variant;
- do not duplicate the NGS variant description itself in `case_facts`;
- do not infer absent tests, normal results, negative history, or clinical significance.
Before returning, survey the authoritative case from beginning to end. Every explicit patient or test fact must be represented by `provisional_disease`, `variants`, or `case_facts`; otherwise add the missing fact.
