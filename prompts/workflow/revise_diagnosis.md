# Re-ground a user-revised diagnosis

## Task

Re-ground the user's requested diagnostic revision against the existing diagnostic evidence without changing the model's original adjudication.

Use only the user's requested revised diagnostic label/downstream category, `diagnostic_evidence.md`, and the existing `adjudication.json`. Apply the shared patient-result semantics in `SKILL.md`.

## Task-specific rules

- The requested `refined_disease` must be one exact value from `allowed_refined_diseases` in `diagnostic_evidence.md`.
- Ground the revision only in supplied case facts and retrieved diagnosis cards.
- Do not invent supporting facts, criteria, cards, tags, or IDs.
- Do not alter top-level `status`, `provisional_disease`, `refined_disease`, `diagnostic_label`, `driven_by`, `criterion_assessment`, or `reason` from the original model adjudication.
- If the requested revision cannot be grounded in retrieved diagnosis evidence, do not manufacture support. Return a concise explanation that the revision is not supportable; do not produce a modified adjudication.

## Output contract

When the revision is supportable, return the complete updated adjudication JSON with only these changes from the supplied `adjudication.json`:

- `user_review.decision` = `"disagree"`;
- `user_review.diagnostic_label` = the grounded revised label;
- `user_review.refined_disease` = one exact `allowed_refined_diseases` value;
- `user_review.reason` = a concise evidence-bounded reason;
- `user_review.card_tags` = one or more exact supporting six-character diagnosis `card_tag` values;
- `downstream_filter_disease` = `user_review.refined_disease`.

Return JSON only when a grounded revision is possible.

## Final check

Before returning, verify privately that every changed field is permitted above, all cited card tags are copied exactly from the supplied diagnostic evidence, and the top-level model adjudication is otherwise byte-for-byte semantically unchanged.
