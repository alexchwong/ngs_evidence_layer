---
name: ngs-evidence-layer
description: Routes NGS evidence/report requests to the default categorical workflow or an explicitly selected registered workflow.
---

## Model-step execution

You are the model executor for this workflow.

When a step is described as a **model step**, perform that reasoning yourself in the current session and write the required output. Do not delegate it on your own initiative: do not call another model yourself, invoke an LLM API yourself, or merely describe what another model should do.

Use repository scripts wherever the selected workflow names them, and only there.

# NGS Evidence Layer — workflow router

This file routes the request only. The selected workflow's `SKILL.md` is authoritative for execution.

## Workflow selection

Read `workflows/registry.json` and resolve exactly one workflow before reading case-specific inputs.

- No workflow selector: use `default_workflow` from the registry (`categorical-v1`).
- `--diagnosis-first`: resolve the registry alias `diagnosis-first` (`diagnosis-first-v1`).
- `--diagnosis-first-v1`: select `diagnosis-first-v1` explicitly.
- `--legacy`: resolve the registry alias `legacy` (`legacy-v1`).
- `--legacy-v1`: select `legacy-v1` explicitly.
- Any other explicit `--<workflow-id>`: select that exact enabled workflow only if it is registered.
- Never infer a workflow from files already present in a work directory. Workflow state is established by the selected workflow's setup command and subsequently enforced deterministically.

After selection, read only the registered workflow's `SKILL.md` and follow it exactly.

## Mode compatibility

The default `categorical-v1` workflow supports `ngs-report`, `nel-demo`, `nel-validate`, and `nel-validate-function`.

`diagnosis-first-v1` supports the same four modes and remains available through `--diagnosis-first` or `--diagnosis-first-v1`.

`evidence-block`, `evidence-block manual`, and `evidence-to-report` are legacy-only. If one of these is requested without an explicit legacy selector, stop and state that the mode requires `--legacy` or `--legacy-v1`; do not silently route it to legacy.

Examples:

```text
ngs-report
ngs-report --diagnosis-first
ngs-report --diagnosis-first-v1
ngs-report --legacy
nel-validate-function 3B
nel-validate-function 3B --diagnosis-first
nel-validate-function 3B --legacy
```
