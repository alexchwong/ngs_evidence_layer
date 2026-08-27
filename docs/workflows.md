# Reporting workflow development

This guide explains how NEL keeps reporting workflows isolated, how to clone the current
workflow safely, and where to make changes in the clone.

For end-user reporting, see `../README.md`. For general repository maintenance and releases,
see `DEVEL.md`.

## Contents

- [Separation model](#separation-model)
- [Current workflows](#current-workflows)
- [Clone the current workflow](#clone-the-current-workflow)
- [Modify the cloned workflow](#modify-the-cloned-workflow)
- [Validate the cloned workflow](#validate-the-cloned-workflow)
- [Promote or remove a workflow](#promote-or-remove-a-workflow)

## Separation model

NEL separates reporting runtime code into three layers.

| Layer | Location | Responsibility |
|---|---|---|
| Stable dispatch | `scripts/` | Resolve the workflow bound to a work directory and call its declared entrypoints. |
| Shared mechanics | `scripts/core/` and `workflows/common.py` | Policy-neutral corpus, retrieval, rendering, card-tag, citation, provenance, and mechanical workflow helpers. |
| Workflow behaviour | `workflows/<workflow>/` | Workflow-specific orchestration, retrieval policy, rendering policy, prompts, audit policy, report representation, and optional runtime commands. |

The stable dispatch layer must not contain branches such as `if workflow == ...` for a
particular pipeline. Shared core code must likewise remain workflow-neutral. Behaviour
that may legitimately differ between pipelines belongs in the workflow package.

### Registry and workflow metadata

`workflows/registry.json` is the top-level registry. It declares:

- `default_workflow`;
- optional aliases such as `legacy`;
- each registered workflow's directory and enabled state.

Each workflow package contains its own `workflow.json`. This metadata declares the
workflow ID, Python package, entrypoint modules, supported modes, skill path, debug
artifact allowlist, and status.

There are therefore two different files named `workflow.json`:

- `workflows/<workflow>/workflow.json` is committed workflow metadata;
- `<work-dir>/workflow.json` is runtime state written by `scripts/setup_workflow.py`.

The runtime state binds a work directory to exactly one workflow. Re-running setup cannot
silently reopen that directory as a different workflow; use a new work directory instead.

### Dispatch path

The normal deterministic path is:

```text
user selector
  -> SKILL.md router
  -> workflows/registry.json
  -> selected workflows/<workflow>/SKILL.md
  -> scripts/setup_workflow.py
  -> <work-dir>/workflow.json
  -> stable CLI in scripts/
  -> scripts/workflow_registry.py
  -> entrypoint declared by workflows/<workflow>/workflow.json
  -> workflow implementation
  -> scripts/core/ primitives where shared mechanics are needed
```

The important stable CLIs are:

- `scripts/run_case.py` -> `case_pipeline` entrypoint;
- `scripts/retrieve.py` -> `retrieval` entrypoint;
- `scripts/render.py` -> `rendering` entrypoint;
- `scripts/report_audit.py` -> `audit_policy` entrypoint;
- `scripts/package_run.py` -> artifact allowlist from workflow metadata;
- `scripts/workflow_runtime.py` -> optional `runtime` entrypoint.

A workflow can therefore change implementation without requiring workflow-specific
copies of these CLIs.

## Current workflows

| Workflow | Status | Purpose |
|---|---|---|
| `terraced-v6` | supported product | Final supported workflow; isolated WHO5/ICC/WHO5 reasoning, combined downstream domains, audited evidence resolution, and final synthesis. |
| `terraced-v5` | legacy/development | Earlier terraced workflow retained in source for comparison and regression only. |
| `terraced-v4` | legacy/development | Earlier terraced workflow retained in source for comparison and regression only. |
| `terraced-v3` | legacy/development | Scheduler-based terraced workflow retained in source for comparison and regression only. |
| `terraced-v2` | legacy/development | Earlier terraced workflow retained in source for comparison and regression only. |
| `terraced-v1` | legacy/development | First terraced workflow derived from categorical-v1. |
| `categorical-v1` | legacy/development | Diagnosis-first evidence retrieval retained in source for historical comparison. |
| `diagnosis-first-v1` | legacy/development | Previous diagnosis-first summarisation workflow retained in source for historical comparison. |
| `legacy-v1` | legacy/development | Previous adjudication-first/evidence-block pipeline retained in source for historical comparison. |

The supported root `SKILL.md` and `nel.py` facade always target `terraced-v6`. Registered legacy workflows are a developer/source concern and are excluded from the normal release payload.

## Clone the current workflow

Create a new workflow from the current default workflow from the repository root:

```bash
python scripts/devel_workflow.py new \
  --from terraced-v6 \
  --name <new-workflow-id>
```

Workflow IDs must contain lowercase letters, digits, and single hyphens only, for example:

```text
diagnosis-first-v2
experimental-summary-v1
```

The helper performs the mechanical clone. It:

1. copies only the selected source workflow package into a new workflow package;
2. rewrites the cloned workflow ID, package imports, paths, and local references;
3. sets `cloned_from` to the selected source workflow ID and `status` to `development`;
4. registers the new workflow as enabled in `workflows/registry.json`;
5. leaves `default_workflow` unchanged;
6. runs the structural workflow check before returning success.

It does **not** copy shared repository contracts such as `scripts/core/`, the shared
case prompts under `prompts/workflow/`, the corpus, schemas, or assay scope. Reporting policy, citation rules, formatting rules, and canonical reporting rules are workflow-owned inside each reporting workflow package, including `categorical_v1` and `diagnosis_first_v1`, so clones can diverge without changing other workflows.

Immediately verify the clone explicitly:

```bash
python scripts/devel_workflow.py check <new-workflow-id>
```

You can run it without changing the default by using its explicit selector, for example:

```text
ngs-report --<new-workflow-id>
nel-validate 1A --<new-workflow-id>
```

## Modify the cloned workflow

Make experimental behaviour changes inside `workflows/<new-workflow-package>/` whenever
possible. The package directory uses underscores while the workflow ID uses hyphens.

For diagnosis-first-derived workflows such as `categorical-v1` and `diagnosis-first-v1`, the main ownership boundaries are:

| File/path | Change it when you want to change... |
|---|---|
| `SKILL.md` | Model-step order, allowed inputs, branching, validation loops, or operator interaction. |
| `prompts/` | Workflow-specific model instructions, formatting, citation behaviour, or rule-view presentation. |
| `case_pipeline.py` | Deterministic sequencing of retrieval/rendering stages and workflow-owned intermediate files. |
| `retrieval.py` | Which cards are selected or how diagnosis/downstream retrieval policy behaves. |
| `rendering.py` | Workflow-specific evidence presentation while reusing shared rendering primitives. |
| `audit_policy.py` | Workflow-specific report-draft structural or semantic validation policy. |
| `runtime.py` | Optional workflow-specific setup assets and deterministic runtime commands. |
| `report_yaml.py` | Workflow-specific YAML templates, validation, assembly, and deterministic final rendering. |
| `workflow.json` | Entrypoints, supported modes, packaged debug artifacts, and workflow status. |

### Keep shared code shared

Do not edit `scripts/run_case.py`, `scripts/retrieve.py`, `scripts/render.py`, or other
stable dispatchers merely to add a new workflow. Register the workflow and implement the
existing declared interface instead.

Move code into `scripts/core/` or `workflows/common.py` only when the behaviour is truly
policy-neutral and should remain identical across workflows. Shared modules must not
import, name, or branch on a particular workflow.

### Shared prompts and rules

The intentionally shared workflow prompts are limited to:

- `prompts/workflow/capture_case.md`;
- `prompts/workflow/structure_case.md`;
- `config/ngs-panel-scope.md` remains a shared assay contract.

Reporting policy is workflow-owned. For diagnosis-first this includes
`reporting_rule_policy.md`, `citation_rules.md`, `format_report.md`, and
`agreed_reporting_rules.md` under `workflows/diagnosis_first_v1/prompts/`. Legacy owns
its three reporting prompts under `workflows/legacy_v1/prompts/` while continuing to use
the legacy canonical `rules/agreed_reporting_rules.md`. Edit a shared source only when
the change is intended for every workflow that consumes it.

### Entrypoints and runtime commands

`workflow.json` maps logical entrypoint names to modules. The structural checker requires
non-empty `case_pipeline`, `retrieval`, `rendering`, and `audit_policy` entrypoints.
Additional entrypoints are allowed when a stable dispatcher uses them.

For deterministic commands needed only by one workflow, prefer the optional `runtime`
entrypoint and dispatch them through:

```bash
python scripts/workflow_runtime.py <command> --work-dir <work-dir>
```

This avoids adding workflow-specific commands or branching to the stable CLI layer.

### Artifact manifest

Keep the `artifacts` list in the cloned `workflow.json` synchronized with the files a
completed run must contain. `scripts/package_run.py` uses this list as the required debug
ZIP allowlist and fails if any declared artifact is missing.

If you add, rename, or remove a workflow-owned intermediate, update this list as part of
the same change.

## Validate the cloned workflow

Use validation in increasing scope.

First check registry, metadata, entrypoints, package paths, status, artifact metadata,
and Python syntax:

```bash
python scripts/devel_workflow.py check <new-workflow-id>
```

Then run the relevant unit tests for the changed components and, before considering the
workflow usable, run representative end-to-end validation cases with the explicit
workflow selector. At minimum, verify that the cloned workflow runs to completion and
that the accepted/default workflow still runs independently.

For broad workflow changes, finish with the full repository test suite:

```bash
python -m unittest discover -s tests -v 2>&1
```

Do not expect two model-driven workflows to produce byte-identical reports. Validation
should establish that each pipeline completes, respects its deterministic contracts, and
produces outputs that can be audited and packaged.

## Promote or remove a workflow

### Promote

Promotion is deliberate; cloning never changes the default.

When a development workflow is ready:

1. validate it structurally and end-to-end;
2. change its `status` in `workflows/<workflow>/workflow.json` as appropriate;
3. change `default_workflow` in `workflows/registry.json` only when it should become the default;
4. add any intended alias explicitly in `workflows/registry.json`;
5. update root `nel.py` and `SKILL.md` only if the supported product workflow itself changes;
6. keep `release/skill.txt` limited to the supported product workflow unless that product decision changes;
7. update `README.md`, `NEWS.md`, and release/version metadata as required;
8. run the release checks in `DEVEL.md`.

### Remove an abandoned development workflow

If a cloned experiment is abandoned before release:

1. remove its entry and any aliases from `workflows/registry.json`;
2. delete its `workflows/<workflow-package>/` directory;
3. remove any release-manifest or documentation references added for it;
4. rerun `scripts/devel_workflow.py check` on the remaining workflows and the relevant tests.

Never delete a workflow that must remain available for reproducibility or an advertised
legacy selector without first defining its compatibility/replacement policy.

---

## Legacy public interfaces

The repository previously exposed workflow selectors such as `--legacy`, `--diagnosis-first`, and `--terraced-v1` through `--terraced-v5`, together with legacy `evidence-block`, `evidence-block manual`, and `evidence-to-report` modes. It also exposed workflow-local/system-temporary working-directory behaviour, including the `->project` modifier.

These interfaces are retained here only as historical/developer context. The supported product interface is now root `nel.py`, which always targets `terraced-v6` and writes user runs under root `runs/<run-id>/`. Legacy workflow source remains in the development repository but is not part of the supported release surface.
