# Card content rules

- One card represents one independently useful, directly supported clinical assertion.
- `genes` contains only genes participating in that assertion. Every gene listed in `genes` must be explicitly named in the interpretation.
- `diseases` records exact source-supported clinical applicability; derived ancestors are indexing terms only and do not broaden scope. Every disease listed in `diseases` must be explicitly identified in the interpretation by its canonical name or an accepted source-disease alias.
- The interpretation must not depend on an unexplained paper-local cohort, arm, group, stratum, protocol, or author-defined label. Replace such a label with the short clinical meaning that defines the population, exposure, treatment, genotype, disease state, or eligibility criterion; generalize to that meaning alone when the local label adds no clinical value.
- Do not merge distinct assertions merely because they share a gene, disease, category, paragraph, table, or census claim.
- **Parallel-gene consolidation exception:** when separate census claims differ only by gene identity and otherwise make the same clinical assertion with the same disease scope, category, population, treatment/comparator, clinical role or outcome, direction, thresholds, qualifiers, exceptions, and evidence basis, represent them with one card. Union the participating genes and write one interpretation that explicitly names every gene. Do not consolidate when any clinically material element differs. This card-level consolidation does not alter Phase 1 census atomicity.
