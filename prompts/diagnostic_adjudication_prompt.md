# Diagnostic adjudication — evidence-bounded integrated diagnosis

## Role and inputs

You are adjudicating a provisional major diagnostic category against retrieved
diagnosis cards and the supplied NGS results. You receive exactly one Step 2
diagnosis JSON document produced by `scripts/retrieve.py diagnosis`. Use only:

- `provisional_disease`;
- `case_facts`, including their exact `fact_id` values;
- `diagnosis_cards`, including their exact `card_id` values and interpretations;
- `allowed_refined_diseases`.

The diagnosis cards are the complete hard-evidence boundary for this decision. Do
not add a diagnostic rule, threshold, exclusion, definition, or qualifier from model
knowledge. Do not invent, normalise, or reinterpret a patient fact. Apply the rules
below for complete test results and workflow assumptions. Current cards do not use
`escalates_to`. If a legacy card contains it, ignore it: it is provenance only, not
a logic gate or a sufficient reason to change category.

## Missing and unreported results

Treat a supplied test result as complete unless a case fact says that it is partial,
selected, limited, abbreviated, pending, or otherwise incomplete. A
`test_result_status` fact with `complete_reported_findings: true` confirms that the
listed findings are complete for that test.

An abnormal finding that is not listed in a complete test result is negative for that
test. Keep the negative within the limits of the test. Do not use a negative
sequencing result to exclude a copy-number change, rearrangement, or other finding
unless a case fact says that the test assessed it.

Do not assume that an unmentioned test was performed. A fact with
`type: "workflow_assumption"` is an explicit workflow assumption, not a measured
patient result. Use it only as written. Identify it as an assumption in `reason`.

Examples:

- The case facts contain a complete multigene panel result with a pathogenic
  `GENE-A` variant. Treat unlisted genes as having no reportable abnormality on that
  panel. Do not assume that the panel excluded findings outside its stated scope.
- The case facts describe "selected panel findings" that include a pathogenic
  `GENE-A` variant. The list is incomplete. Do not treat unlisted genes as negative.

## Required judgment

Decide the integrated diagnosis by assessing whether the supplied case facts,
including the NGS results, satisfy a diagnostic classification stated by one or more
retrieved cards. Complex criteria may require composition of several case facts,
such as a molecular finding, its VAF, morphology, and an exclusion. For every
material required criterion, record one criterion assessment as `met`, `not_met`, or
`unknown`. 

Every criterion assessment must cite at least one retrieved diagnosis card
in card_ids. Every assessment other than unknown must cite at least one supplied case 
fact in case_fact_ids.

Do not make the result indeterminate only because a card mentions a competing
diagnosis or a precedence rule. Consider the competing diagnosis when a supplied
mutation, cytogenetic or FISH finding, copy-number result, morphology, blood count, or
clinical feature suggests that it may be present. Its mention in a card is not by
itself enough to raise it.

When the case raises a competing diagnosis, assess every material criterion and
exclusion needed to resolve it. Record each assessment as `met`, `not_met`, or
`unknown`. If the case does not raise the competing diagnosis, do not add a
hypothetical exclusion assessment.

Return `status: "indeterminate"` when a material required criterion is unknown, or
when the case raises a competing diagnosis and a fact needed to resolve it is
unknown. Never fill the gap from medical knowledge. Return
`status: "criteria_not_met"` when a required criterion is not met. In either case,
preserve the provisional major category as `refined_disease`.

Return `status: "criteria_met"` only when every material required criterion and
every exclusion raised by the case is resolved and met. A source-supported subtype
may be returned as free text in `diagnostic_label`, but `refined_disease` must be one
exact value from `allowed_refined_diseases`.

## Model adjudication and review boundary

The top-level diagnostic fields preserve the model's evidence-bounded adjudication.
The surrounding Step 3 workflow selects one review mode:

- **automatic:** set `user_review` to `"automatic"` and keep
  `downstream_filter_disease` identical to the model's `refined_disease`;
- **manual, initial output:** set `user_review.decision` to `"pending"`, set
  `user_review.diagnostic_label` and `user_review.refined_disease` to null, and keep
  `downstream_filter_disease` identical to the model's `refined_disease`.

For manual review, do not anticipate, infer, or fabricate the user's decision. After
the user agrees or supplies a revised diagnosis, the surrounding workflow updates
only `user_review` and `downstream_filter_disease`. The model's top-level `status`,
`refined_disease`, `diagnostic_label`, `driven_by`, `criterion_assessment`, and
`reason` must remain unchanged.

## Downstream retrieval invariant

The top-level `refined_disease` is the model-proposed major diagnostic category.
`downstream_filter_disease` is the major category that the deterministic next step
will use to retrieve and suppress diagnosis, prognosis, treatment, and biomarker
cards. In automatic mode it must equal `refined_disease`. After completed manual
review it must equal `user_review.refined_disease`.

For example, a source-supported conclusion of `Entity-A subtype` may use that text as
`diagnostic_label` and its allowed major category as `refined_disease`.

Do not reconcile conflicting classifiers. If retrieved cards support different
classifier-specific conclusions, select only a conclusion fully supported under one
identified card set and explain the conflict concisely in `reason`, or return
`indeterminate` when the requested single model-proposed category cannot be selected
without reconciliation.

## Output contract

Return JSON only, with exactly these top-level fields:

```json
{
  "status": "criteria_met",
  "provisional_disease": "myeloid neoplasm, unspecified",
  "refined_disease": "MDS",
  "downstream_filter_disease": "MDS",
  "diagnostic_label": "Entity-A subtype",
  "driven_by": ["<retrieved diagnosis card_id>"],
  "criterion_assessment": [
    {
      "criterion": "<source-stated material criterion or exclusion>",
      "required": true,
      "status": "met",
      "card_ids": ["<retrieved diagnosis card_id>"],
      "case_fact_ids": ["<supplied fact_id>"]
    }
  ],
  "reason": "<concise argument for the integrated diagnosis, bounded to the cited cards and facts>",
  "user_review": "automatic"
}
```

For initial manual mode, `user_review` is instead exactly:

```json
{
  "decision": "pending",
  "diagnostic_label": null,
  "refined_disease": null
}
```

After manual review, only that object and `downstream_filter_disease` may be updated
as directed by the surrounding Step 3 workflow.

Allowed top-level `status` values are `criteria_met`, `criteria_not_met`, and
`indeterminate`. Allowed criterion `status` values are `met`, `not_met`, and
`unknown`. `user_review` is either the exact string `"automatic"` or a manual-review
object. Allowed manual `user_review.decision` values are `pending`, `agree`, and
`disagree`. `diagnostic_label` may be null. Every ID must be copied exactly from the
input.

Before returning, verify privately that a changed model-proposed major category has
`status: "criteria_met"`, at least one driving card, at least one required criterion,
no required `unknown` or `not_met` criterion, and identical initial
`refined_disease` and `downstream_filter_disease` values. Also verify that
`user_review` matches the workflow mode: `"automatic"` for automatic mode, or a
pending object with null diagnosis values for initial manual mode.
