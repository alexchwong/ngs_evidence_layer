# Automatic validation marking

Automatic marking is a post-report sidecar for canonical `proforma-v1` validation runs. It does not participate in clinical interpretation and it does not determine whether the clinical report itself is complete.

## Scope

- Applies to dynamically discovered `nel-validate-*` suites.
- Does not automatically mark `nel-demo`.
- Uses the normal configurable `marking` model role from the frozen pipeline profile.
- Uses the canonical case registry and `validation/mark_validation_report.md`; there is no second marking-criteria source.
- Existing external marking ZIP generation remains supported.

## Isolation boundary

Evaluator-only marking criteria must not be retrieved before a non-empty `report-final.md` exists. Automatic marking therefore begins only after clinical report finalisation. The browser marking endpoint reads only already-materialised marking artifacts and status; it never retrieves criteria itself.

Clinical report completion and marking completion are independent. A provider error, malformed marker response, or stale marking result does not invalidate `report-final.md`. A later `nel.py run` may retry marking without regenerating the clinical report. For a validation batch, however, the parent remains operationally `marking_incomplete` until every clinically complete child also has current marking; this is a retryable sidecar state, not a clinical failure.

## Per-run artifacts

Validation runs may contain:

```text
report-final.md
marking.md
marking.json
functional.json          # Dublin only
logs/marking-status.json
```

`marking.md` is the accepted human-readable marker response. `marking.json` is the normalized deterministic representation and includes the SHA-256 of the exact `report-final.md` that was marked. If the report changes, the previous marking becomes `stale` and is not treated as current.

The normalized response requires every canonical RxCy criterion exactly once, no unknown criteria, legal `met` booleans, legal failure modes, and the expected R1-R5 rubric/category structure. The marking call is made through the standard model-task machinery, so prompt input, model output, reasoning, retries, validation and usage/cost remain visible in the existing model observability artifacts.

## Dublin F1-F9

The marking model evaluates RxCy only. It must not receive, infer or emit F1-F9 functional results.

After a valid RxCy response, `validation/scripts/score_functional_dublin.py` deterministically maps the result using the machine-readable specification in `validation/docs/dublin_functional_criteria.md`. The result is written to `functional.json`. If that deterministic artifact is missing while the RxCy marking remains current, it can be regenerated without another model call.

## Batch behavior

Each validation child is marked independently using its own frozen pipeline and report. There is no batch-marking LLM.

The batch parent deterministically writes:

```text
batch-marking.md
batch-marking.json
```

The aggregate records marked/total, per-case R1-R5 outcomes, criterion failure-mode counts and, for Dublin, per-case and aggregate F1-F9 results. A batch with all clinical reports written but unresolved marking is exposed as `marking_incomplete`, not `complete`. It may be resumed solely to retry child marking that is `pending`, `failed` or `stale`; completed reports are not rerun. The parent becomes `complete` only after every required child marking is current.

## CLI and browser status

Single-run JSON status exposes a `marking` object with states such as:

- `not_applicable`
- `pending`
- `complete`
- `failed`
- `stale`

Batch status includes aggregate marking state and `marked/total`.

The browser middle column has a **Marking** tab beside **Dissent**. It shows single-run marking, batch-child marking, batch aggregate marking, and Dublin functional results. Validation progress appends a presentation-only **Marking** segment after the declarative clinical phases; marking is not added to `workflow/default.yaml`. Failed/stale marking leaves the report clinically complete while exposing **Retry marking**. The same marking model call also appears in the generic **Models** tab because it uses the normal model observability index.

## Pipeline migration

`marking` is a required `proforma-v1` model role. Existing custom or frozen pipeline YAMLs created before automatic marking must add the role before those profiles pass current exact-role validation. No automatic profile migration is performed.

## Execution ownership

`validation/scripts/package_marking.py` owns only evaluator prompt rendering,
strict response validation, report-hash binding, status inspection, deterministic
artifact persistence, and external ZIP packaging. It must not import or invoke a
proforma executor or provider client.

`workflows/proforma_v1/automatic_marking.py` owns model execution. Provider
marking uses the normal proforma model-task runner. Native-self marking uses a
bounded handoff adapter that persists each attempt under the normal
`model_steps/.../attempts/` observability layout. Exhausted marking failure is
non-blocking for the clinical report; a later root `nel.py run` starts a fresh
marking call root and preserves the exhausted history.

The canonical shipped pipeline defaults live under
`workflows/proforma_v1/pipelines/`. Root `config/pipelines/` copies are managed by
`workflows/proforma_v1/devel_sync.py`; both locations must not be edited as
independent sources.
