---
name: ngs-evidence-layer
description: Runs the canonical proforma-v1 NGS Evidence Layer product through the root nel.py interface.
---

# NGS Evidence Layer

The **repository root** is the directory containing this `SKILL.md` file and `nel.py`. Before running any command, use that directory as the working directory. All relative paths below are relative to the repository root.

The canonical supported workflow is `proforma-v1`. Use the root `nel.py` facade for all product runs. `terraced-v6` is retained only as an explicit legacy/reproducibility path selected with root `--legacy`; never route a normal request to it.

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

Root user configuration is in `config/`, including `config/pipelines/`, and belongs exclusively to canonical `proforma-v1`. Run artefacts are always under `runs/<run-id>/`.
`nel.py` is the only public facade. Normal new runs use `proforma-v1`; explicit `--legacy` setup uses the retained legacy implementation with workflow-local settings/pipelines. Existing runs are dispatched by their frozen workflow manifest. Do not reproduce executor stage logic in the root skill.

## NGS report

For a request containing a clinical case and `ngs-report`:

1. Preserve the supplied case verbatim in a temporary Markdown file outside `workflows/`.
2. Run:

   ```bash
   python nel.py setup --mode ngs-report --case <case-file> [--run-id <id>] [--pipeline <pipeline>]
   ```

   Omit `--pipeline` unless the user selected one; the default comes from `config/settings.json`.
3. Record the returned `RUN_ID`.
4. Call:

   ```bash
   python nel.py run --run-id <id>
   ```

5. If `STATUS=handoff`, read every file named by `MANIFEST`, follow the named contract exactly, and write the requested `OUTPUT`. Then repeat step 4.
6. Stop only when `STATUS=complete`.
7. Read `runs/<run-id>/report-final.md` and return that report to the user.

Never use the old `->project`, system-temp, historical workflow-selector flags, or workflow-local run interfaces for a new product run.

## Demo and validation modes

Map supported requests to root setup as follows:

```text
nel-demo example N       -> python nel.py setup --mode nel-demo --example N
nel-validate ID          -> python nel.py setup --mode nel-validate --case-id ID
nel-validate-function ID -> python nel.py setup --mode nel-validate-function --case-id ID
nel-validate-brief ID    -> python nel.py setup --mode nel-validate-brief --case-id ID
nel-validate-dual ID     -> python nel.py setup --mode nel-validate-dual --case-id ID
```

Then use the same repeated `python nel.py run --run-id <id>` loop. Do not read expected results or marking criteria before report generation completes.

## Existing runs

Use:

```bash
python nel.py runs
```

to survey all run directories by workflow progress, or:

```bash
python nel.py runs --incomplete
```

to find incomplete runs. Use `python nel.py status --run-id <id>` before resuming an existing run.

## Legacy workflow

`proforma-v1` remains canonical. Only when the user explicitly requests the prior product workflow, create it through the root facade:

```bash
python nel.py setup --legacy --mode <mode> [mode arguments] [--pipeline <pipeline>]
```

`--legacy` selects `terraced-v6` and its workflow-local settings/pipelines; it never reuses root `config/settings.json` or `config/pipelines/`. For self execution, follow the same repeated `python nel.py run --run-id <id>` handoff loop. Existing legacy runs are also resumed with ordinary `python nel.py run --run-id <id>` because their frozen manifest records the workflow. Do not pass `--legacy` to `run` or `status`.

Do not route product requests to `legacy-v1`, `diagnosis-first-v1`, or terraced-v1 through terraced-v5.
