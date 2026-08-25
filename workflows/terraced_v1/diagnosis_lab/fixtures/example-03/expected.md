# Expected — Case 3

Exercises: `myeloid neoplasm, unspecified` as the provisional disease; whether
disease-agnostic diagnosis cards carry the CHIP/CCUS distinction into retrieval.

Expected behaviour:
- The workflow starts from `myeloid neoplasm, unspecified` and must not upgrade the major category from model knowledge alone.
- Any refinement must be supported by retrieved diagnosis evidence and supplied case facts.
- If the corpus does not establish a different diagnosis, the provisional major category should be preserved.
