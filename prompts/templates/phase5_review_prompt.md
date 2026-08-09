# Phase 5 — focused independent review

## Active phase and output contract

You are the independent reviewer for **only the proposed Phase 5 additions** to one publication.

Read-only inputs:
- `paper.md`
- `paper.phase5-provisional.json`
- `phase5_review_prompt.md`

Return exactly one file: `paper.phase5-review.json`.

You must be a different model from the top-level `extraction_model` in `paper.phase5-provisional.json`. Do not edit cards or evidence and do not create a final package.

## Review

Review every proposed card exactly once.

For each card determine whether:
- every material assertion in the interpretation is supported by its paired evidence;
- the evidence fragments occur verbatim in `paper.md`;
- disease, population, treatment, variant class, threshold, exclusions and other qualifiers are not broadened;
- composite evidence forms one defensible assertion without evidence laundering;
- table evidence reconstructs the applicable value, headers and qualifiers;
- the card is independently useful rather than materially redundant with another card in this provisional supplement.

A passed card contains only its `card_id` and `verdict: "pass"`. A failed card must use the existing review failure-details structure and a precise suggested action.

Use the existing Phase 3 review JSON shape:
- same `paper_id` and `round` as the Phase 5 provisional;
- `reviewer_model` is this model's exact identity;
- `extraction_model_reviewed` exactly equals the provisional `extraction_model`;
- `result` is `review_complete`;
- publication type normally passes unchanged because Phase 5 does not change it; use `verified_by_phase3: true` for a passing verdict because the original package already completed Phase 3;
- card counts and ordering exactly match the Phase 5 provisional.


Return exactly `paper.phase5-review.json`. `confirm.py` later performs deterministic validation of this review against the proposed cards and source.
