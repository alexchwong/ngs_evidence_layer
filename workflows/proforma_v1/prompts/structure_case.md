# Structure the case
Return JSON only using exactly this shape:
```json
{
  "provisional_disease": "short source-faithful provisional morphologic disease description",
  "diagnosis_status": "new|progress",
  "morphologic_diagnosis_origin": "supplied|inferred",
  "patient_age": "source-faithful supplied age text or null",
  "bootstrap_cmcs": ["one or more exact allowed CMC values"],
  "variants": [
    {
      "variant_id": "V1",
      "gene": "GENE",
      "description": "GENE complete reported variant description",
      "event_type": "sequence_variant|fusion|copy_number|structural_variant|other|unknown",
      "vaf": "source-faithful supplied VAF text or null"
    }
  ],
  "detected_variants_summary": "One sentence listing every detected NGS variant, or stating that no NGS variants were detected.",
  "ngs_result_completeness": "complete|incomplete",
  "ngs_no_variants_detected": [],
  "case_facts": [
    {"fact_id": "C1", "kind": "short kind", "value": "source-faithful patient fact"}
  ]
}
```
Diagnosis-status rules:
- Return `diagnosis_status: new` for a diagnostic work-up in which the current specimen is being used to establish the disease diagnosis.
- Return `diagnosis_status: progress` when the case explicitly describes a follow-up, progress, response, restaging, post-treatment, or surveillance specimen for an established prior haematological disease.
- For `progress`, preserve the explicitly supplied established disease as `provisional_disease` even when the current marrow shows treatment response or remission. Current morphology, blast percentage, molecular clearance, and other response findings belong in `case_facts`; they do not replace the underlying disease label.
- For `progress`, preserve any new findings that may indicate progression or transformation. Do not force the current findings to remain unchanged merely because a prior disease is established; WHO5/ICC decide downstream whether the disease has progressed or transformed.
- If `diagnosis_status` is not available in a legacy structured case, downstream core treats it as `new`.
Morphologic diagnosis rules:
- For `new`, only an explicit supplied diagnostic label counts as a morphologic/pathologic diagnosis. Copy that label source-faithfully into `provisional_disease` and return `morphologic_diagnosis_origin: supplied`.
- For `progress`, an explicitly supplied established prior diagnosis is the disease context and may populate `provisional_disease`; return `morphologic_diagnosis_origin: supplied` for that supplied disease context even when the current specimen is described only by response/status morphology.
- Descriptive marrow or tissue findings are not diagnoses. Statements describing cellularity, lineage patterns, dysplasia, blast percentages, or other observations remain `case_facts` unless the case separately supplies an explicit diagnostic label.
- For `new`, if no morphologic/pathologic diagnosis is explicitly supplied, return `provisional_disease: "No morphologic diagnosis supplied"` and `morphologic_diagnosis_origin: inferred`. Do not invent a provisional disease label from descriptive morphology, cytopenias, other nonspecific laboratory findings, or NGS findings. Molecular refinement occurs downstream.
- `bootstrap_cmcs` are retrieval scaffolds, not diagnoses. For `new`, when there is no explicit morphologic diagnosis, morphology is explicitly normal or non-diagnostic, no NGS variants are detected, and current cytogenetic/other molecular findings are absent, normal, pending, unavailable, not performed, or otherwise non-diagnostic, use `no_haematological_malignancy` as the bootstrap CMC.
- This is an internal no-established-diagnosis routing sentinel; it does not assert that a myeloid neoplasm has been excluded. Do not use this sentinel merely because a `progress` specimen is in remission or molecularly negative.
For `patient_age`:
- copy the explicitly supplied patient age source-faithfully when present;
- return `null` when patient age is not supplied;
- do not infer age from dates, disease context, treatment history, or other indirect information;
- also preserve the original age statement in `case_facts` when it is explicitly supplied, so the authoritative source fact remains available in the ordinary clinical context.
For `variants`:
- preserve every reported NGS molecular finding;
- when the case explicitly states that no NGS variants were detected, or gives an equivalent unequivocal negative NGS result, return `variants: []` and state that no NGS variants were detected in `detected_variants_summary`;
- never create a pseudo-variant representing "no variants detected" or another negative result;
- `gene` is the reported uppercase gene symbol used to identify the finding in the case;
- `description` begins with the exact `gene`, followed by the complete reported molecular finding description;
- preserve all supplied transcript, cDNA, protein, VAF, partner-gene, and other molecular detail in `description`;
- `event_type` classifies the form of the reported molecular event using only the supplied case information:
  - `sequence_variant`: a sequence-level alteration within a gene, including substitutions, insertions, deletions, indels, duplications, internal tandem duplications, and other sequence-level changes;
  - `fusion`: a named gene-to-gene or chimeric fusion event;
  - `copy_number`: a finding principally described as copy-number gain, loss, amplification, deletion, or other dosage change;
  - `structural_variant`: a larger rearrangement or structural genomic event that is not best represented as a named fusion or copy-number event;
  - `other`: a supplied molecular event that clearly does not fit the preceding classes;
  - `unknown`: the supplied information is insufficient to classify the event type; do not guess;
- `vaf` contains the source-faithful VAF text/value when explicitly supplied for that molecular finding, otherwise `null`;
- do not derive a VAF from other measurements or infer one when it is absent;
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
- do not omit a cytogenetic, FISH, copy-number, structural, or other finding because it involves the same gene as an NGS molecular finding;
- do not duplicate the full NGS molecular finding description itself in `case_facts`;
- do not infer absent tests, normal results, negative history, or clinical significance.
Before returning, survey the authoritative case from beginning to end. Every explicit patient or test fact must be represented by `provisional_disease`, `variants`, or `case_facts`; otherwise add the missing fact.
