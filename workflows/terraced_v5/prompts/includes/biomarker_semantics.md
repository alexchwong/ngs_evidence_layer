# Biomarker / MRD interpretation boundaries

MRD suitability is a distinct clinical property.

Do NOT infer MRD suitability from:
- diagnostic importance;
- disease classification;
- prognostic importance;
- a recommendation to test the variant at diagnosis;
- high VAF;
- technical detectability; or
- persistence of the mutation over time.

`suitable_mrd` requires affirmative MRD-specific support; diagnostic, prognostic, or technical-detectability evidence is insufficient.

Use `unsuitable_mrd` when the supplied information specifically indicates that the variant should not be used as a stand-alone marker of residual disease, including because it may persist in clonal haematopoiesis, pre-leukaemic, or ancestral clones.

If no MRD-specific evidence supports suitability, do not infer suitability from evidence belonging to another clinical domain.

Use:
- `uncertain` when MRD-specific evidence is incomplete, conflicting, or insufficient to determine suitability;
- `no_effect` when no meaningful MRD implication is identified.

If evidence specifically argues against MRD use, that negative MRD evidence takes precedence over unrelated diagnostic or prognostic relevance.
