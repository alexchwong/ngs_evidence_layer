# Expected — Case 4

Exercises: `not_assessed` naming a gene individually rather than dropping it. At
least one gene here should fall outside every ingested publication; which one
depends on what has actually been ingested, so check the corpus before treating a
result as a failure.

What, if anything, is a usable follow-up marker here?

Expected behaviour:
- The known major diagnostic category remains AML unless retrieved diagnostic evidence supports a change.
- Every submitted gene should remain visible to the workflow; a gene absent from the corpus should be named as not assessed rather than omitted.
- Follow-up-marker statements in the final report must be limited to biomarker evidence actually retrieved from the current corpus.
