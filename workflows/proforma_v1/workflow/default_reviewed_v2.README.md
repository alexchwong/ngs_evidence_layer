# `default_reviewed_v2` — bounded owner reasoning audit

`default_reviewed_v2` is a `default`-derived workflow that adds an immediate reasoning audit after each clinical owner while retaining the clinical owner proformas and the existing downstream evidence/report pipeline.

## Contract

Each owner result is converted deterministically into a proposition/premise packet. A coherence reviewer returns only a list of disputes. Python validates whether each dispute is structurally addressable; it does **not** decide whether the clinical criticism is true.

Addressable disputes are passed to the dedicated `reasoning_adjudication` role. The adjudicator independently decides whether each criticism is upheld and restates upheld criticisms in plain English. Only upheld criticisms are returned to the original clinical owner. The owner receives its normal task context, prior assessment, and adjudicator-restated criticism; it is explicitly allowed to reject a criticism it cannot derive itself.

A separate adjudication role provides another reasoning pass. It does not guarantee a different underlying model unless the selected profile assigns a different model to that role.

## Audit states

Each completed owner audit resolves to one of:

- `sound` — a valid audit produced no disputes.
- `disputed` — at least one structurally addressable dispute was produced and therefore requires adjudication.
- `unusable` — the audit output was structurally invalid, over-produced disputes, or contained no addressable dispute despite claiming a defect.

If the coherence model never produces parseable output, the workflow can fail before a completed audit state is recorded. That engine-level exhausted-review artifact remains a deferred improvement; do not interpret absence of an audit state as `sound`.

## Correction cycles and provenance

Owner retries are bounded by the workflow review budget. Every accepted owner attempt is archived under `audit_v2/owner-cycles/<owner>/<cycle>/`; this archive is the authoritative per-cycle record.

`audit_v2/<owner>-history.yaml` records the accepted proposition/premise states and the exact upheld adjudication that caused a retry. After cycle `N` is accepted, the correction-response sidecar compares it against cycle `N-1` using the **previous cycle's upheld challenge**. This causal linkage is important: a corrected cycle will commonly audit as sound, so using its current disputes would erase both successful corrections and bad capitulations from the history.

For treatment, premise matching is category-independent at therapy level where there is exactly one implication on each side. If multiplicity makes identity ambiguous, the sidecar records `comparison_status: ambiguous`, sets `premise_status_changed: null`, declines the capitulation comparison, and records that decline in the current history cycle rather than guessing.

The deterministic capitulation guard is only a tripwire. It uses an explicit reviewed downgrade map and can surface a downgrade that follows an upheld background-knowledge criticism. It does not determine which clinical conclusion is correct.

## Adjudication validation and resume

Adjudication output is schema- and coverage-validated deterministically under both provider and native-self execution. Invalid adjudication output is cleared so the same adjudication step can be retried. The rejection reason is stored in `self_validation_feedback` and persisted in workflow control state so a fresh native-self process receives the deterministic validation feedback. Repeated invalid adjudication reaches a persisted non-retryable terminal failure through the shared terminal-failure helper.

## Terminal policy

Unresolved owner reviews use the configured reviewed-v2 terminal policy. Terminal semantic failures are persisted in `logs/workflow-failure.json`; control state is saved before the terminal exception is raised. Diagnosis withholding also clears variant assessments so downstream concurrent-pathology output cannot leak from a WHO conclusion that the terminal policy withheld.

## Motivating failures

Run 007-7 motivated the background-knowledge adjudication and cross-cycle capitulation protection: a correct GATA2 germline-suspicious conclusion could be displaced by an incorrect VAF criticism. Run 008-8 motivated richer diagnosis packet premises and explicit concurrent-pathology reasoning around MYD88/LPL-WM. These are motivating cases, not special-cased rules.

## Cost

The workflow has 61 steps. The main steady-state cost is one small coherence audit per clinical owner plus adjudication only when a structurally addressable dispute exists. Owner reruns occur only for upheld disputes. Model-call cost must still be measured on the validation set; the architectural target is a mean increase of no more than two calls per run relative to the chosen baseline.

## Known limitations / deferred work

- A coherence model that never produces parseable output can still fail before an `unusable` audit artifact is committed.
- `model-operations.json` is not the authoritative per-cycle owner log; use `audit_v2/owner-cycles/`.
- Native-self declared-check completion has an engine-level short-circuit predating this workflow; reviewed-v2 applies its correctness-bearing validation downstream in Python instead.
- Native-self cycle archives do not preserve pre-normalisation raw model transport bytes.
- A richer report-routing policy for unresolved review notices is proposed separately and is not implemented here.

## Verification

Run the repository test suite and workflow check before promotion. In addition, run the validation-set regression and compare reportable element counts/schema IDs and mean model calls with the pre-change baseline. The requested 007-7 and 008-8 replay runs are intentionally not part of this implementation bundle.
