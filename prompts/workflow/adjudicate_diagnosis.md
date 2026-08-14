# Adjudicate the diagnosis

## Task

Adjudicate the provisional major diagnostic category using exactly one Step 2 Markdown document (`diagnostic_evidence.md`) produced by `scripts/retrieve.py diagnosis`.

Use only:

- `case_major_category`;
- free-text `provisional_disease`;
- `case_facts` and exact `fact_id` values;
- `diagnosis_cards`, their interpretations, and exact `card_id` values;
- `allowed_refined_diseases`.

Apply the shared patient-result semantics in `SKILL.md`.

Diagnosis cards are the complete hard-evidence boundary. Do not add diagnostic rules, thresholds, exclusions, definitions, or qualifiers from model knowledge. Do not invent, normalise, or reinterpret patient facts.

## Task-specific rules

Determine whether the supplied case facts, including NGS results, satisfy a diagnostic classification stated by retrieved cards. Criteria may require multiple facts, such as a molecular finding, VAF, morphology, and exclusions.

For every material required criterion or exclusion assessed:

- record `status` as `met`, `not_met`, or `unknown`;
- cite at least one retrieved diagnosis card in `card_ids`;
- if `status` is not `unknown`, cite at least one supplied fact in `case_fact_ids`.

Assess a competing diagnosis only when supplied case facts raise it; mention in a card or precedence rule alone is insufficient. When raised, assess every material criterion and exclusion needed to resolve it. Do not add hypothetical exclusion assessments for diagnoses not raised by the case.

Set the top-level result as follows:

- `indeterminate`: any material required criterion is `unknown`, or a case-raised competing diagnosis cannot be resolved because a needed fact is unknown;
- `criteria_not_met`: any required criterion is `not_met`;
- `criteria_met`: every material required criterion and every case-raised exclusion is resolved and met.

`provisional_disease` is the supplied clinicomorphological starting label and need not be a controlled-vocabulary value. `refined_disease` must be one exact value from `allowed_refined_diseases`. For `indeterminate` or `criteria_not_met`, keep `refined_disease` within the supplied `case_major_category`. Move outside that major category only with `criteria_met`. A source-supported or supplied subtype/entity may be free text in `diagnostic_label`.

Do not reconcile conflicting classifiers. If cards support different classifier-specific conclusions, select a conclusion only if it is fully supported under one identified card set and explain the conflict concisely in `reason`. Otherwise return `indeterminate`.

If `diagnosis_cards` is empty:

- do not reclassify;
- set `status` to `"indeterminate"`;
- set `refined_disease` and `downstream_filter_disease` to `case_major_category`;
- preserve the supplied `provisional_disease` as `diagnostic_label`;
- set `driven_by` and `criterion_assessment` to `[]`;
- state in `reason` that no corpus diagnosis evidence was retrieved.

Top-level diagnostic fields preserve the model adjudication. Set `user_review` and the initial `downstream_filter_disease` exactly as required by the current workflow mode in `SKILL.md`. Do not anticipate a manual-review decision.

## Output contract

Return JSON only, with exactly these top-level fields:

```json
{
  "status": "criteria_met",
  "provisional_disease": "myelodysplastic neoplasm with increased blasts-2 (MDS-IB2)",
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
  "reason": "<concise argument bounded to the cited cards and facts>",
  "user_review": "automatic"
}
```

For initial manual mode, `user_review` is exactly:

```json
{
  "decision": "pending",
  "diagnostic_label": null,
  "refined_disease": null,
  "reason": null,
  "card_ids": []
}
```

Allowed top-level `status`: `criteria_met`, `criteria_not_met`, `indeterminate`.
Allowed criterion `status`: `met`, `not_met`, `unknown`.
Allowed manual `user_review.decision`: `pending`, `agree`, `disagree`.
`diagnostic_label` may be null. Copy every ID exactly from the input.

## Final check

Before returning, verify privately:

- any `refined_disease` outside the supplied `case_major_category` has `criteria_met`, at least one driving card, at least one required criterion, and no required `unknown` or `not_met` criterion;
- initial `downstream_filter_disease` equals model `refined_disease` except for the explicit no-diagnosis-card fallback above, where both still equal the selected major category;
- `user_review` matches the workflow mode declared by `SKILL.md`.
