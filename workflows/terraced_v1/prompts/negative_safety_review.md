# Terraced-v1 exceptional-negative safety audit

Compare the structured patient case, the current uncited report draft, and the quarantined negative facts.

## The question you must answer

Would omission of any quarantined fact cause the report to give an **incorrect answer to an explicit patient-specific diagnostic, test-result, or management question**?

Restore a quarantined fact only when the answer is yes. The negative fact itself must be necessary to prevent a wrong or materially misleading patient-level conclusion.

If the report remains correct but would merely become more complete, nuanced, explanatory, cautious, comprehensive, or contextual by restoring the fact, **do not restore it**.

Return only:

```yaml
restore:
  - fact_id: diagnosis-3
    after_sentence_id: diagnosis-1
```

An empty list is valid and should be preferred when no quarantined fact meets the strict rescue rule:

```yaml
restore: []
```

`after_sentence_id` must be an existing sentence ID from the same clinical domain. Use `null` to place the fact at the end of its clinical domain; if that domain has no current heading, the deterministic renderer will create it in the standard domain order.

## Permitted rescue situations

A quarantined negative may be restored only when omission would otherwise do at least one of the following:

- fail to directly answer an explicit diagnosis or differential supplied for this patient because the negative finding contradicts that named hypothesis;
- leave a named disease entity incorrectly supported when absence of its defining lesion is itself necessary to reject that entity;
- omit the actual negative result of a dedicated clinically requested test, such as a disease-specific MRD assay or targeted familial-variant test;
- give the wrong patient-level management conclusion when the absence itself directly determines the relevant treatment, eligibility, or contraindication decision;
- leave an already retained report sentence factually wrong or materially misleading because the quarantined fact directly disproves what that sentence says or necessarily implies.

The threshold is intentionally high. A negative fact used only inside the reasoning chain is not reportable merely because it helped derive a retained positive conclusion.

## These are NOT rescue reasons

Do not restore a fact merely because:

- it helped establish a positive diagnosis or classification;
- it satisfied an exclusion, wild-type, modifier, eligibility, prognostic, or treatment premise;
- it was part of the reasoning chain for another retained conclusion;
- it provides a caveat, useful context, reassurance, completeness, nuance, or explanation;
- it explains why a detected variant does not alter diagnosis, prognosis, treatment, or classification;
- it explains why a detected variant should not be used as an MRD marker when the report can instead state the appropriate positive MRD marker(s);
- it says a mutation is not prognostic or does not change a prognostic tier;
- it says a therapy, evidence subgroup, framework, or score does not apply;
- it states that no prognostic, treatment, MRD, germline, or other category-specific finding was identified;
- it says there is no evidence for a concurrent second pathology;
- a multiparameter score cannot be calculated from missing non-molecular variables.

Prefer a concise retained positive statement over restoring its negative converse. For example, if the retained report can state which molecular findings are appropriate MRD markers, do not restore separate statements listing detected variants that should not be used for MRD.

## Strict operation boundary

- Select only supplied quarantined `fact_id` values.
- Do not write replacement prose: restored facts are inserted verbatim by deterministic code.
- Do not alter the report, create new clinical assertions, make citation decisions, or search for evidence.
- Each restored fact may appear only once.
