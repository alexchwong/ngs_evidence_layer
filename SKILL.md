---
name: ngs-evidence-layer
description: Runs the canonical default NGS Evidence Layer workflow through the root nel.py interface.
---
# NGS Evidence Layer

The **repository root** is the directory containing this `SKILL.md` file and `nel.py`. Before running any command, use that directory as the working directory. All relative paths below are relative to the repository root.

The supported product workflow is `default`, implemented by `workflows/proforma_v1/workflow/default.yaml` and exposed through the root `nel.py` facade. Normal runs use this workflow and its `default` config without requiring explicit selectors.

The default workflow configuration is `workflows/proforma_v1/configs/default/default.yaml`. Omitted `--config` therefore uses the recommended setup; `--config legacy` is retained only for explicit reproducibility. The selected config is frozen at setup and inherited by later `run`/`status` calls.

## Model-step execution

When `nel.py run` returns `STATUS=handoff`, you are the model executor for that bounded step. Perform the reasoning yourself in the current session using only the returned manifest inputs and contract, write exactly the requested output file, then call `python nel.py run --run-id <id>` again.

Do not delegate a self handoff to another model or LLM API. Do not infer missing evidence from general haematology knowledge.

## Public interface

From the repository root, use only the public `nel.py` CLI:

```bash
python nel.py init
python nel.py config-check
python nel.py setup ...
python nel.py run ...
python nel.py status ...
python nel.py runs ...
```

Root user configuration is in `config/`, including `config/pipelines/`, and belongs to the canonical default workflow. Run artefacts are always under `runs/<run-id>/`.

`nel.py` is the only public facade. Normal new runs use the canonical `default` workflow and its `default` config. Both are frozen at setup and subsequent `run`/`status` calls inherit them. `--config legacy` is available only when the user explicitly requests the previous baseline. Existing runs are dispatched by their frozen workflow manifest. Do not reproduce executor stage logic in the root skill.

## NGS report

For a request containing a clinical case and `ngs-report`:

1. Preserve the supplied case verbatim in a temporary Markdown file outside `workflows/`.
2. Run:

   ```bash
   python nel.py setup --mode ngs-report --case <case-file> [--run-id <id>] [--pipeline <pipeline>] [--config legacy]
   ```

   Omit `--pipeline` unless the user selected one; the default comes from `config/settings.json`. Omit `--config` for normal runs so the supported `default` config is used. Use `--config legacy` only when the user explicitly requests the previous baseline configuration.
3. Record the returned `RUN_ID`.
4. Call:

   ```bash
   python nel.py run --run-id <id>
   ```
5. If `STATUS=handoff`, read every file named by `MANIFEST`, follow the named contract exactly, and write the requested `OUTPUT`. Then repeat step 4.
6. Stop only when `STATUS=complete`.
7. Read `runs/<run-id>/report-final.md` and return that report to the user.

Never use the old `->project`, system-temp, or workflow-local run interfaces for a new product run.

## Demo and validation modes

For a bundled demo:

```text
nel-demo example N -> python nel.py setup --mode nel-demo --example N
```

Validation modes are data-driven. Do not keep or infer a fixed suite list in this skill. Resolve the currently registered validation suites and case IDs from the central registry:

```bash
python validation/case_registry.py list
```

Then map a validation request to:

```bash
python nel.py setup --mode <registered-validation-suite> --case-id <case-id>
```

For normal runs, do not add a workflow or config selector. Append `--config legacy` only when the user explicitly requests the previous baseline configuration. Then use the same repeated `python nel.py run --run-id <id>` loop.

During validation report generation, read only the selected clinical case supplied by setup. Do not retrieve or read evaluator-only marking criteria before `report-final.md` is complete.

## Existing runs

Use:

```bash
python nel.py runs
```

to survey all run directories by workflow progress, or:

```bash
python nel.py runs --incomplete
```

to find incomplete runs. Use `python nel.py status --run-id <id>` before resuming an existing run. The run's frozen `workflow_definition` and `workflow_config` are authoritative; do not try to change them when resuming.

