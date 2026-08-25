---
name: ngs-evidence-layer
description: Routes NGS evidence/report requests to the default terraced-v6 workflow or an explicitly selected registered workflow.
---

## Model-step execution

You are the model executor for this workflow.

When a step is described as a **model step**, perform that reasoning yourself in the current session and write the required output. Do not delegate it on your own initiative: do not call another model yourself, invoke an LLM API yourself, or merely describe what another model should do.

Use repository scripts wherever the selected workflow names them, and only there.

# NGS Evidence Layer — workflow router

This file routes the request only. The selected workflow's `SKILL.md` is authoritative for execution.

## Workflow selection

Read `workflows/registry.json` and resolve exactly one workflow before reading case-specific inputs.

- No workflow selector: use `default_workflow` from the registry (`terraced_v6`).
- `--diagnosis-first`: resolve the registry alias `diagnosis-first` (`diagnosis-first-v1`).
- `--diagnosis-first-v1`: select `diagnosis-first-v1` explicitly.
- `--terraced`: resolve the registry alias `terraced` (`terraced-v6`).
- `--terraced-v1`: select `terraced-v1` explicitly.
- `--terraced-v2`: select `terraced-v2` explicitly.
- `--terraced-v3`: select experimental `terraced-v3` explicitly.
- `--terraced-v4`: select experimental `terraced-v4` explicitly.
- `--terraced-v5`: select experimental `terraced-v5` explicitly.
- `--terraced-v6`: select `terraced-v6` explicitly.
- `--legacy`: resolve the registry alias `legacy` (`legacy-v1`).
- `--legacy-v1`: select `legacy-v1` explicitly.
- Any other explicit `--<workflow-id>`: select that exact enabled workflow only if it is registered.
- Never infer a workflow from files already present in a work directory. Workflow state is established by the selected workflow's setup command and subsequently enforced deterministically.

After selection, the next repository file you read must be the registered workflow's `SKILL.md`; before reading it, do not run commands or infer execution syntax from user-facing mode names. Then follow that workflow `SKILL.md` exactly.

## Mode compatibility

The default workflow is `terraced-v6`.

### Available modes

- `ngs-report` — generate a full NGS report
- `nel-demo example <N>` — run repository example N
- `nel-validate <case-id>` — validate against case_summary.md
- `nel-validate-function <case-id>` — validate against case_functional.md
- `nel-validate-brief <case-id>` — validate against validation_brief.md
- `evidence-block` — generate evidence block only (legacy-v1 only)
- `evidence-block manual` — generate evidence block with manual review (legacy-v1 only)
- `evidence-to-report` — convert existing evidence to report (legacy-v1 only)

### Workflow support

`categorical-v1` supports the five standard modes.

`diagnosis-first-v1` supports the five standard modes and is available through `--diagnosis-first` or `--diagnosis-first-v1`.

`terraced-v1` supports the five standard modes and is selected explicitly with `--terraced-v1`.

`terraced-v2` supports the five standard modes and is selected explicitly with `--terraced-v2`.

`terraced-v3` supports the five standard modes and is selected explicitly with `--terraced-v3`. It is experimental. Its scheduler can additionally be selected with `--scheduler domain|evidence-first|variant-centric|global-ledger|adaptive-microtask`; when omitted, the v3 default is `domain`.

`terraced-v4` supports the five standard modes and is selected explicitly with `--terraced-v4`. It is experimental.

`terraced-v5` supports the five standard modes and is selected explicitly with `--terraced-v5`. It is experimental.

`terraced-v6` supports the five standard modes and is the default workflow. It is selected explicitly with `--terraced-v6` or implicitly with `--terraced`.

`evidence-block`, `evidence-block manual`, and `evidence-to-report` are legacy-only. If one of these is requested without an explicit legacy selector, stop and state that the mode requires `--legacy` or `--legacy-v1`; do not silently route it to legacy.

Examples:

```text
ngs-report
ngs-report --diagnosis-first
ngs-report --diagnosis-first-v1
ngs-report --terraced
ngs-report --terraced-v1
ngs-report --terraced-v2
ngs-report --terraced-v3
ngs-report --terraced-v4
ngs-report --terraced-v5
ngs-report --terraced-v6
ngs-report --legacy
nel-validate-function 3B
nel-validate-brief 8
nel-validate-brief 1 --terraced-v3 --scheduler global-ledger
nel-validate-function 3B --diagnosis-first
nel-validate-function 3B --legacy
```
