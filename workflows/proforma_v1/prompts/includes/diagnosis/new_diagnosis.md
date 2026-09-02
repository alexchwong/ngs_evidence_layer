For `diagnosis_status: new`, use the no-established-neoplasm fallback only when all of the following are true:
- no morphologic diagnosis was supplied (`morphologic_diagnosis_origin: inferred`);
- no NGS variants are detected; and
- no supplied cytogenetic or other molecular finding currently establishes or refines a diagnosis, including when those studies are absent, normal, pending, unavailable, not performed, or otherwise non-diagnostic.

When all of those conditions are met:
- do not manufacture a myeloid neoplasm from descriptive marrow findings or cytopenias;
- return `schema_disease: no_haematological_malignancy`;
- return `diagnosis: "No myeloid neoplasm established from supplied findings"`;
- return `diagnostic_effect: unchanged`, `variants: []`, and `variant_assessments: []`;
- treat `schema_disease: no_haematological_malignancy` as an internal sentinel only; it does not mean a myeloid neoplasm has been excluded; and
- state in `reason` that the result does not exclude a myeloid neoplasm, that clinical/morphologic correlation is required, and that any explicitly pending diagnostic study remains pending.
