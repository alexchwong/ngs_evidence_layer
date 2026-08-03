# Case 6 — SF3B1 diagnostic adjudication

Exercises: evidence-bounded composition of molecular and morphology facts; changing
the major diagnostic category used for downstream card calling without relying on
`escalates_to`; preserving `MDS-SF3B1` as the specific diagnostic label while using
`MDS` as the downstream disease filter; failing closed if a source-stated required
criterion or exclusion is not supplied.

---

72F with persistent macrocytic anaemia. Bone marrow is reported as showing
insufficient dysplastic change for a diagnosis of MDS. Blasts are not increased.
Iron stain shows 7% ring sideroblasts.

NGS (myeloid panel):
- SF3B1 pathogenic variant, VAF 30%

No other case facts relevant to classifier-specific exclusions are supplied.

Question for the panel: when the retrieved diagnosis card states that these supplied
molecular and ring-sideroblast findings satisfy its criteria, should the major
diagnostic category used for downstream evidence retrieval change to MDS, with
`MDS-SF3B1` retained as the source-supported specific label? If the card states an
additional required exclusion that cannot be resolved from the case, the adjudication
should instead be indeterminate and preserve the provisional major category.