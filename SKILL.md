---
name: ngs-evidence-layer
description: Routes NGS evidence/report requests to the accepted diagnosis-first workflow or an explicitly selected registered workflow.
---

## Model-step execution

You are the model executor for this workflow.

When a step is described as a **model step**, perform that reasoning yourself in the current session and write the required output. Do not attempt to call another LLM, invoke an LLM API, or merely describe what another model should do.

Only use repository scripts for steps explicitly identified as deterministic CLI operations.

# NGS Evidence Layer — workflow router

This file routes the request only. The selected workflow's `SKILL.md` is authoritative for execution.

## Workflow selection

Read `workflows/registry.json` and resolve exactly one workflow before reading case-specific inputs.

- No workflow selector: use `default_workflow` from the registry (`diagnosis-first-v1`).
- `--legacy`: resolve the registry alias `legacy` (`legacy-v1`).
- `--legacy-v1`: select `legacy-v1` explicitly.
- Any other explicit `--<workflow-id>`: select that exact enabled workflow only if it is registered.
- Never infer a workflow from files already present in a work directory. Workflow state is established by the selected workflow's setup command and subsequently enforced deterministically.

After selection, read only the registered workflow's `SKILL.md` and follow it exactly.


## Mode compatibility

The accepted diagnosis-first workflow supports `ngs-report`, `nel-demo`, `nel-validate`, and `nel-validate-function`.

`evidence-block`, `evidence-block manual`, and `evidence-to-report` are legacy-only. If one of these is requested without an explicit legacy selector, stop and state that the mode requires `--legacy` or `--legacy-v1`; do not silently route it to legacy.

Examples:

```text
ngs-report
ngs-report --legacy
ngs-report --legacy-v1
nel-validate-function 3B
nel-validate-function 3B --legacy
```
