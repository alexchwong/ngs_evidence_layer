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
- `--terraced`: resolve the registry alias `terraced` (`terraced-v1`).
- `--terraced-v1`: select `terraced-v1` explicitly.
- `--terraced-v2`: select `terraced-v2` explicitly.
- `--legacy`: resolve the registry alias `legacy` (`legacy-v1`).
- `--legacy-v1`: select `legacy-v1` explicitly.
- Any other explicit `--<workflow-id>`: select that exact enabled workflow only if it is registered.
- Never infer a workflow from files already present in a work directory. Workflow state is established by the selected workflow's setup command and subsequently enforced deterministically.

After selection, the next repository file you read must be the registered workflow's `SKILL.md`; before reading it, do not run commands or infer execution syntax from user-facing mode names. Then follow that workflow `SKILL.md` exactly.

## Mode compatibility

The default `categorical-v1` workflow supports `ngs-report`, `nel-demo`, `nel-validate`, `nel-validate-function`, and `nel-validate-brief`.

`diagnosis-first-v1` supports the same five modes and remains available through `--diagnosis-first` or `--diagnosis-first-v1`.

`terraced-v1` supports the same five modes and remains available through `--terraced` or `--terraced-v1`.

`terraced-v2` supports the same five modes and is selected explicitly with `--terraced-v2`. The `--terraced` alias remains bound to v1 for compatibility.

`evidence-block`, `evidence-block manual`, and `evidence-to-report` are legacy-only. If one of these is requested without an explicit legacy selector, stop and state that the mode requires `--legacy` or `--legacy-v1`; do not silently route it to legacy.

Examples:

```text
ngs-report
ngs-report --diagnosis-first
ngs-report --diagnosis-first-v1
ngs-report --terraced
ngs-report --terraced-v1
ngs-report --terraced-v2
ngs-report --legacy
nel-validate-function 3B
nel-validate-brief 8
nel-validate-function 3B --diagnosis-first
nel-validate-function 3B --legacy
```
