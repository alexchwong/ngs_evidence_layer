# Proforma v1 — native self execution

`proforma_v1` has one selected declarative workflow and two execution adapters. The selected YAML, not this file, owns clinical operations, dependencies, conditions, evidence barriers, self batching, and intentional executor-specific omissions.

## Routing

- Default / explicit self execution: use `workflows/proforma_v1/self.py`.
- Explicit non-self provider: use `workflows/proforma_v1/step.py`.
- Both accept `--workflow <yaml>`. If omitted, both use `workflow/default.yaml`.
- Never infer the clinical stage sequence from this document. Always ask the workflow driver what is next.

## Native-self loop

You are the model executor. Do not call another LLM or model API.

After setup, repeat only this loop:

```text
self.py run
    ↓
STATUS=handoff
    ↓
read exactly the manifest paths printed by self.py
    ↓
perform the requested model task(s) in the current session
    ↓
write exactly the requested output file(s)
    ↓
self.py run again immediately
```

The second `self.py run` invocation performs deterministic parsing, validation, transforms, feedback/retry routing, condition evaluation, and then either returns a repair handoff, the next model handoff, or completion. The host model does not decide which clinical operation follows.

A handoff may contain several independent logical operations when the selected workflow gives them the same self batch group. Complete every output requested by that manifest in one host-model reasoning pass. Each logical output is still validated independently by Python.

If a workflow operation declares native-self execution disabled, `self.py` skips it and records `executor_disabled` in the logical trace. In the shipped default workflow report preservation is intentionally provider-only.

## Setup

```bash
python workflows/proforma_v1/self.py setup \
  --mode <mode> \
  [--case-file <case.md>] \
  [--workflow workflow/custom.yaml] \
  [--work-dir <dir> | --project]
```

Use the exact work directory printed by setup. The selected workflow path and SHA-256 are bound to the run; a changed workflow is rejected on resume.

Then advance with:

```bash
python workflows/proforma_v1/self.py run --work-dir <work-dir>
```

If setup used a non-default workflow, `--workflow` may be repeated on `run` as a consistency assertion, but it is not required: the run already remembers the selected workflow.

## Handoff rules

For `STATUS=handoff`:

1. Read the rendered `prompt`, contract/schema, context, card pool, and other paths in the manifest.
2. Do only the requested model reasoning. Candidate cards may be clinical source material. A PTBG owner operation whose selected workflow declares `evidence.owner_assignment: true` must assign only exact card tags supplied in that owner's card envelope; other owner operations must not invent or leak runtime card tags.
3. Write the complete requested artifact(s), never a patch.
4. Invoke `self.py run` again immediately so deterministic validation can accept, reject, or feed back the result. An invalid PTBG owner assignment is fed back to that owner operation for complete-artifact repair before evidence review proceeds.

Do not manually call historical stage-specific commands to determine progression. They remain compatibility/debug helpers only; `run` is the canonical native-self driver.

## Completion

When `STATUS=complete`, use the printed final artifact paths. `dissent.md` is deterministic and never model-authored.
