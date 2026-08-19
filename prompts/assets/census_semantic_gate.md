# Census semantic gate

Apply this audit to the complete active census within its confirmed `category_scope` (or all five categories when `category_scope` is absent).

## Audit procedure

Perform this as a **source-first census audit**, not as an entry-by-entry proofreading pass:

1. Re-walk the complete paper, including relevant tables and footnotes, while temporarily ignoring the candidate census.
2. Independently reconstruct the expected set of atomic, clinically relevant source assertions inside the confirmed category scope. For each expected assertion, identify its category, participating genes, source locator, and every qualifier needed to preserve meaning and applicability.
3. Compare that independently reconstructed expected set with the candidate census and collect **all** material defects before repairing anything. Look specifically for missing assertions, over-merged assertions, qualifiers split away from the claim they govern, incorrect categories or genes, broadened or weakened summaries, and inadequate locators.
4. Reverse-check every candidate census entry against the source to identify unsupported additions, combinations, interpretations, or scope expansion.
5. Only after the complete audit has been collected may the candidate census be revised; after revision, repeat this source-first audit on the complete revised census.

A census passes only when all of the following are true:

1. **Completeness:** every clinically relevant, paper-supported assertion in the confirmed scope is represented; intentionally out-of-scope categories are not omissions.
2. **Atomicity:** each entry is one Phase 2 retain/reject review boundary. If Phase 2 could reasonably retain one part while rejecting another, the entry is not atomic and must be split.
3. **Qualifier preservation:** disease, population, molecular context, treatment, comparator, threshold, analysis, exception, uncertainty, and other qualifiers required to preserve meaning or applicability remain attached to the assertion they govern and are not split away.
4. **Category correctness:** each entry's category follows `CATEGORY_SEMANTICS` and lies within the confirmed scope.
5. **Gene correctness:** `genes` contains only genes participating in that exact assertion; `genes: []` is used only as permitted by `GENELESS_CLAIM_POLICY`.
6. **Source fidelity:** each summary states only the source-supported assertion and does not broaden, strengthen, combine, or clinically interpret beyond the paper.
7. **Locator adequacy:** each locator identifies the source material supporting that census assertion closely enough for Phase 2 to find and review it.
8. **Publication type:** `publication_type` and `publication_type_basis` are supported by the paper and use the allowed taxonomy.

Audit the whole census, not only previously criticised entries. Do not stop after finding the first defect.

This gate assesses **census quality only**. A census entry is a source-faithful Phase 2 review boundary, not a finished evidence-card interpretation. Do not apply evidence-card eligibility, card interpretation wording, evidence-bundle construction, disease-vocabulary tagging, card consolidation, tagged gene/disease surfacing, or other card-authoring requirements when deciding whether the census passes this gate.
