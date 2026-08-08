# Expected — Case 6

Exercises: evidence-bounded composition of molecular and morphology facts; changing
the major diagnostic category used for downstream card calling without relying on
`escalates_to`; preserving `MDS-SF3B1` as the specific diagnostic label while using
`MDS` as the downstream disease filter; failing closed if a source-stated required
criterion or exclusion is not supplied.

No other case facts relevant to classifier-specific exclusions are supplied.

Question for the panel: when the retrieved diagnosis card states that these supplied
molecular and ring-sideroblast findings satisfy its criteria, should the major
diagnostic category used for downstream evidence retrieval change to MDS, with
`MDS-SF3B1` retained as the source-supported specific label? If the card states an
additional required exclusion that cannot be resolved from the case, the adjudication
should instead be indeterminate and preserve the provisional major category.

Expected behaviour:
- If all source-stated required criteria and exclusions can be satisfied from the supplied facts, the specific label may be `MDS-SF3B1` while the downstream major category is MDS.
- If a required criterion or exclusion is unresolved, adjudication should be indeterminate and preserve `myeloid neoplasm, unspecified` as the downstream major category.
