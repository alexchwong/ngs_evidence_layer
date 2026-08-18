# Terraced-v1 final synthesis

Write the final clinical interpretative report using only the supplied accepted facts.

The input deliberately contains no reasons, cards or citations. Do not add a clinical assertion that is not represented by an input fact.

Requirements:
- Produce concise patient-level prose for clinical haematologists.
- Integrate detected variants into diagnosis rather than creating a separate detected-variants section.
- Use WHO5 diagnostic wording from the accepted diagnosis facts.
- Preserve clinically material qualifications and concurrent pathologies.
- Omit categories with no accepted facts.
- Avoid exhaustive normal-result lists, generic teaching, or statements that a prognostic score cannot be calculated unless the input facts explicitly make that clinically important.
- Write plain Markdown prose under exact standalone bold category headings. Use only `**Diagnosis**`, `**Prognosis**`, `**Treatment Implications**`, `**MRD**`, and `**Germline**`; omit a heading when that category has no reportable fact.
- Put every report sentence under one of those headings and end every sentence with a full stop.
- Every sentence must be directly matchable to one or more accepted facts in the same category. Preserve absence-of-evidence wording; do not strengthen it into a positive negative finding.
- Do not write citations, card tags, a bibliography, or `(no citation required)` markers.
