# Terraced-v1 final synthesis

Perform lossless semantic compression of the supplied retained accepted facts into the final uncited clinical interpretative report.

The retained fact set has already passed reportability policy. You are not a second reportability filter. Every distinct retained fact must remain represented in the report, although multiple overlapping facts may be merged into one sentence when all of their semantic content is preserved.

The input deliberately contains no reasons, cards or citations. Do not add a clinical assertion that is not represented by a retained input fact.

Requirements:
- Preserve every distinct retained accepted fact. Do not discard a retained fact because it seems less important, redundant in context, or clinically obvious.
- You may merge overlapping facts, remove literal repetition, shorten wording, and improve flow only when no retained semantic content or material qualification is lost.
- Produce concise patient-level prose for clinical haematologists.
- Integrate detected variants into diagnosis rather than creating a separate detected-variants section.
- Use WHO5 diagnostic wording from the accepted diagnosis facts.
- Preserve clinically material qualifications and concurrent pathologies.
- Omit categories with no retained facts.
- Write plain Markdown prose under exact standalone bold category headings. Use only `**Diagnosis**`, `**Prognosis**`, `**Treatment Implications**`, `**MRD**`, and `**Germline**`; omit a heading when that category has no retained fact.
- Put every report sentence under one of those headings and end every sentence with a full stop.
- Every sentence must be directly matchable to one or more retained accepted facts in the same category, and every retained accepted fact must be represented by at least one sentence.
- Preserve absence-of-evidence wording; do not strengthen it into a positive negative finding.
- Do not write citations, card tags, a bibliography, or `(no citation required)` markers.
