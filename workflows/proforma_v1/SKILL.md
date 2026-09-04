# Proforma v1 — native self execution

`proforma-v1` is the canonical product workflow family. The repository-root `SKILL.md` and `nel.py` are the public interface; this workflow-local skill documents the internal native-self adapter used behind that facade.

`proforma_v1` has one selected declarative workflow definition and two execution adapters. The selected YAML, not this file, owns clinical operations, dependencies, conditions, evidence barriers, self batching, and intentional executor-specific omissions.

## Routing

- Default / explicit self execution: the public driver is root `nel.py`; it delegates clinical progression to `workflows/proforma_v1/self.py` and owns post-report validation marking.
- Explicit non-self provider: use `workflows/proforma_v1/step.py` after root setup.
- Both workflow-local adapters accept `--workflow <yaml>` for run-time workflow assertions. If omitted, both use the workflow bound during setup.
- The public root facade accepts `--workflow <name>` and resolves it to `workflows/proforma_v1/workflow/<name>.yaml`; `default` is the default public selection.
- Never infer the clinical stage sequence from this document. Always ask the workflow driver what is next.

## Native-self loop

You are the model executor. Do not call another LLM or model API.

After root setup, repeat only the public loop:

```text
nel.py run --run-id <run-id>
    ↓
STATUS=handoff
    ↓
read exactly the manifest paths printed by nel.py
    ↓
perform the requested model task(s) in the current session
    ↓
write exactly the requested output file(s)
    ↓
nel.py run --run-id <run-id> again immediately
```

For clinical handoffs root `nel.py` delegates to `self.py`; after `report-final.md` exists it may instead return the evaluator-only validation-marking handoff. Each subsequent root invocation performs the appropriate deterministic validation/retry routing and returns either a repair handoff, the next handoff, or completion. The host model does not decide which operation follows.

A handoff may contain several independent logical operations when the selected workflow gives them the same self batch group. Complete every output requested by that manifest in one host-model reasoning pass. Each logical output is still validated independently by Python.

If a workflow operation declares native-self execution disabled, `self.py` skips it and records `executor_disabled` in the logical trace. In the shipped default workflow report preservation is intentionally provider-only.

## Setup

Use the root facade for setup so workflow metadata, validation-suite discovery, provider configuration, and public selectors have one entry point:

```bash
python nel.py setup \
  --mode <mode> \
  [--case-file <case.md>] \
  [--workflow <name>] \
  [--work-dir <dir> | --project]
```

Validation suites are discovered from canonical Markdown by `validation/case_registry.py`; this skill does not name or register individual validation suites. Inspect the currently available suites and cases with:

```bash
python validation/case_registry.py list
```

Then select any discovered suite through the root facade:

```bash
python nel.py setup \
  --mode <discovered-validation-suite> \
  --case-id <case-id> \
  --pipeline self
```

Validation setup exposes only the selected `Case summary`. Evaluator-only `Marking criteria` content must not be retrieved or read before `report-final.md` is complete.

Use the exact work directory printed by setup. The selected workflow path and SHA-256 are bound to the run; a changed workflow is rejected on resume. Root-created runs additionally record the public filename-stem selection as `workflow_definition` while retaining `workflow: proforma-v1` for workflow-family dispatch.

Then advance through the public root facade:

```bash
python nel.py run --run-id <run-id>
```

`self.py run` remains the internal clinical-workflow adapter. The root facade owns
the post-report validation-marking sidecar, including native-self marking handoffs.
For a validation run, continue invoking `nel.py run` after `report-final.md` is
created until marking is complete or a non-blocking marking failure is reported.

If setup used a non-default workflow, `--workflow` may be repeated on `run` as a consistency assertion, but it is not required: the run already remembers the selected workflow.

## Handoff rules

For `STATUS=handoff`:

1. Read the rendered `prompt`, contract/schema, context, card pool, and other paths in the manifest.
2. Do only the requested model reasoning. Candidate cards may be clinical source material. A PTBG owner operation whose selected workflow declares `evidence.owner_assignment: true` must assign only exact card tags supplied in that owner's card envelope; other owner operations must not invent or leak runtime card tags.
3. Write the complete requested artifact(s), never a patch.
4. Invoke root `nel.py run --run-id <run-id>` again immediately so deterministic validation can accept, reject, or feed back the result. An invalid PTBG owner assignment is fed back to that owner operation for complete-artifact repair before evidence review proceeds.

Do not manually call historical stage-specific commands to determine progression. They remain compatibility/debug helpers only; `run` is the canonical native-self driver.

## Validation marking handoff

A validation run may produce a `STATUS=handoff` with `STAGE=validation_marking` only after the clinical report has already completed. This is an evaluator-only sidecar, not another clinical workflow stage.

For that handoff:

1. Read only the printed marking prompt/inputs.
2. Write the complete requested marking response to the printed output path.
3. Run root `python nel.py run --run-id <run>` again so deterministic marking validation can accept or reject it.

The marking response is validated against the canonical RxCy criteria and is recorded through the same model observability/retry machinery as other roles. Marking failure does not make the clinical report incomplete. If the final report changes, previous marking is stale and must be regenerated.

For `nel-validate-dublin`, do not produce F1-F9 yourself. The model marks RxCy only; Python deterministically writes `functional.json` afterwards.

## Completion

Clinical completion is determined by `report-final.md`; automatic validation marking is a separate non-blocking sidecar owned by the root `nel.py` facade. A validation run may therefore have a complete clinical report while marking is `pending`, `failed`, or `stale`. Continue the root run loop when a marking handoff is returned. `dissent.md` is deterministic and never model-authored.

For validation runs, clinical `STATUS=complete` and automatic marking status are deliberately separate. Root `nel.py status --json` exposes the marking sidecar state (`pending`, `complete`, `failed`, or `stale`). The browser **Marking** tab displays the accepted marking and Dublin functional translation where applicable, while the **Models** tab exposes the underlying `marking` model call and retries.
