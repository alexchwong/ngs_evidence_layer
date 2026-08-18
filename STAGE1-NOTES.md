# Stage 1 — script-driven model steps for categorical-v1

Status: complete and tested. `SKILL.md` is deliberately unchanged, so the workflow
still runs exactly as before. The new driver is independently exercisable.

## Files

New, all workflow-local:

- `workflows/categorical_v1/models.json` — model registry. Two profiles: `self`
  (default) and `local-llm`. Every `local-llm` model ID is a placeholder.
- `workflows/categorical_v1/model_registry.py` — profile and role resolution.
  Standard library only, so a registry check works before `.env` exists.
- `workflows/categorical_v1/model_client.py` — OpenAI-compatible client. Standard
  library only. Distinguishes HTTP error, unreachable endpoint and malformed
  completion; strips at most one wrapping code fence.
- `workflows/categorical_v1/model_steps.py` — the step table. Single source of
  truth for `ORDER` and for every permitted input set.
- `workflows/categorical_v1/step.py` — the uniform front end.
- `workflows/categorical_v1/prompts/patient_result_semantics.md` — extracted
  invariants, appended to every model step's bundle via `COMMON_PROMPTS`.

Modified:

- `scripts/workflow_registry.py` — `write_workflow_state` gains an optional
  `model_profile`, written only when set and preserved across rewrites. This is
  the only shared file touched. `diagnosis-first-v1` and `legacy-v1` are unaffected.

Tests:

- `tests/test_categorical_model_steps.py` — 20 tests covering registry resolution
  order, bundle construction including the conditional category input set,
  mode gating, and all four exit codes.

## Step sequence

`ORDER` is `1a 1b 2 3a 3b 4 5 6a 6b1 6b2 6b3 6b4 6b5 6c 7`.

`6b1`–`6b5` map onto `report_yaml.SUMMARY_SECTIONS` — diagnosis, prognosis,
treatment, mrd, germline — derived from that constant rather than restated, so the
two cannot diverge.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Step completed and validated |
| 1 | Deterministic failure |
| 10 | Handoff — role bound to the session model; bundle written, complete the output and re-invoke with `--complete` |
| 20 | Step not required — the category manifest forbids a model call; continue |

## Commands

```bash
# configuration check, no work directory needed
python workflows/categorical_v1/model_registry.py --profile local-llm

# setup; the profile is persisted into workflow.json
python workflows/categorical_v1/step.py setup --mode nel-demo --example 1
python workflows/categorical_v1/step.py setup --mode ngs-report --case-file <file>
python workflows/categorical_v1/step.py setup --mode nel-validate --case-id 3B \
    --model-profile local-llm

# one step
python workflows/categorical_v1/step.py 3a --work-dir <work-dir>
python workflows/categorical_v1/step.py 3a --work-dir <work-dir> --complete

# whole sequence, unattended (requires a delegating profile)
python workflows/categorical_v1/step.py --all --work-dir <work-dir> --profile local-llm

# bundles, also produced automatically by step 7
python workflows/categorical_v1/step.py package-bundles --work-dir <work-dir>
```

## Implementation decisions taken during the build

**Workflow-local placement.** Everything lives in `workflows/categorical_v1/`
rather than `scripts/`, per the decision not to generalise yet. Because the driver
lives inside the package it imports `model_steps` directly and asserts the work
directory is bound to `categorical-v1`, rather than resolving the workflow
dynamically. Generalising later is a move-and-reintroduce exercise, not a no-op.

**No changes to `setup_workflow.py`.** `step.py setup` calls `setup_workflow()` as
a library function and then writes the profile and `case-source.md` itself. This
keeps `--model-profile` off a script that two other workflows also use.

**Deterministic steps are dispatched, not shelled out.** `step.py` calls
`runtime.run()` and `run_case.run_stage()` directly and prints their output lines
unchanged, so `CMC_CHANGED=` and `CATEGORY_*=` still appear as they do today.
`scripts/workflow_runtime.py` is untouched and remains a working fallback.

**`case-source.md` is written in every mode.** In validation modes it mirrors the
`case.md` that `setup_assets` already wrote. Step 1A remains gated out of both
validation modes, so it is never read there. Writing it unconditionally keeps the
artifact allowlist uniform, which the shared packager requires.

**Output promotion.** Each delegated attempt is written to
`.model-steps/<step>/attempt-<n>.output` and validated in place at the real output
path; if validation fails the previous content (the deterministic template) is
restored. A failed run therefore never leaves an unvalidated draft where a later
`--complete` could accept it. Nothing is deleted.

**Retries.** Three attempts for `1a`, `1b`, `3a`, `5`; two for `3b` and `6b1`–`6b5`,
where failures are dominated by word-limit overshoot and a third attempt rarely
helps. Overridable per invocation with `--max-attempts`.

**Step 5 inputs are unconditional.** The CMC branch is already carried inside
`reporting-rules-remainder.md`, which deterministic step 4 writes with or without
injected diagnosis context. The branch decision stays in Python and is never
re-derived in the step specification. The conditional input set that the spec
anticipated appears instead at `6b*`, where `report-summary-dx.yaml` is included
only when `cmc_changed` is false.

**Bundle packaging.** A separate `ngs-report-model-steps.zip`, produced by step 7
alongside the existing debug ZIP. `package_run.py` and the artifact allowlist are
untouched.

## Verification performed

- Registry check prints three bindings for both profiles.
- `setup` in `nel-demo` and `nel-validate-function`; profile persisted correctly.
- Step 1A under `self` exits 10, writes a bundle containing only the declared
  prompt, the common prompt and `case-source.md`.
- Step 1A `--complete` exits 0; 1B exits 10 with a two-input bundle.
- Step 1A refused in `nel-validate-function` (exit 1).
- Driver refuses a `diagnosis-first-v1` work directory.
- Full repository suite: 408 passed. Three pre-existing failures
  (`test_package_marking.py` ×2, `test_workflow_prompts.py` ×1) are unrelated —
  they concern root `SKILL.md` text and a `validation/case_functional_manifest.md`
  that is absent from the supplied archive.

## Before Stage 2

1. Replace the three placeholder model IDs in `models.json` with the exact strings
   from `GET /v1/models`.
2. Walk the full sequence under `self` for one case, completing each handoff. This
   proves the driver end to end without touching `SKILL.md`.
3. Then Stage 2: rewrite `SKILL.md` around `step.py`, delete the per-category
   instructions that duplicate `prompts/formatting/*.md`, add the execution-contract
   section, and add the test asserting the `SKILL.md` command list equals `ORDER`.

## One risk to note

For the packaged-ZIP-upload use case, Step 0 runs `pip install -r requirements.txt`.
In a chat sandbox without network access that will fail, and the workflow needs
PyYAML and jsonschema. `model_registry.py` and `model_client.py` are standard
library only and will work regardless, but the deterministic steps will not. Worth
deciding before you rely on the upload path.
