After the primary diagnosis is fixed, assess every detected registry variant exactly once in `variant_assessments`. The variant registry is the authoritative list of detected variants; when it is empty, return `variant_assessments: []`.
- `diagnostic_for_primary`: contributed to defining or refining the final primary disease under the active classification framework.
- `nonspecific`: does not provide a sufficiently strong diagnostic signal for the final primary disease or a distinct other pathology.
- `diagnostic_for_other_pathology`: consider only variants that did not contribute to the primary diagnosis; use only when supplied authority cards support a distinct pathology and do not show the variant as expected, defining, or refining in the final primary diagnosis. Mere occurrence in another disease is insufficient.
- `other_pathology` must be null unless `classification` is `diagnostic_for_other_pathology`; then name the most specific distinct disease entity, disease family, or lineage-level pathology justified by the supplied authority cards.
- `variant_assessments[].reason` is one concise variant-level explanation of the classification.
