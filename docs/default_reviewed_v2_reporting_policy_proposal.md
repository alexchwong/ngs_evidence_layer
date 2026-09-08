# Proposal: reviewed-v2 unresolved-review reporting policy

Status: proposal only; **not implemented** by the reasoning refactor.

## Questions to decide

1. Whether a `retain_with_review_flag` terminal mode should exist.
2. Whether germline should default to that mode rather than withholding.
3. Whether a `germline_uncertain` row under unresolved review remains reportable.
4. How an unresolved-review notice becomes a durable report element.

## Proposed routing contract

If implemented, unresolved-review state should be stored as a structured deterministic artifact keyed to the affected owner/proposition, converted to an explicit report element before report-block synthesis, and preserved through report writing/finalization. The notice must identify that independent reasoning review remained unresolved without prescribing a replacement clinical answer.

A retained clinical element and its review notice should travel together. Report-block conversion must not silently drop the notice, merge it into ordinary evidence text, or allow a preservation model to remove it. Under native-self execution where the preservation model may be disabled, deterministic block construction must still surface the same notice.

## Germline policy decision

Do not make `retain_with_review_flag` the germline default until the report-routing contract above is implemented and tested. In particular, a `germline_uncertain` row must not become reportable merely because a new terminal enum exists; reportability should be an explicit policy decision with tests for both retained and withheld states.

## Required tests before implementation

- unresolved review creates one durable structured notice;
- retained element and notice both survive block conversion and final report writing;
- withholding removes the clinical element but preserves an appropriate review record;
- provider and native-self reports expose equivalent notices;
- report preservation cannot remove or materially soften the notice;
- no terminal setting silently changes behaviour without a visible report effect.
