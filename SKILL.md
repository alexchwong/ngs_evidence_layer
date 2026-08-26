---
name: ngs-evidence-layer
description: Runs the supported terraced-v6 NGS Evidence Layer product through the root nel.py interface.
---

# NGS Evidence Layer

The supported workflow is `terraced-v6`. Every other directory under `workflows/` is legacy/development code. Do not invoke workflow-internal CLIs and do not ask the user to edit anything under `workflows/`.

## Model-step execution

When `nel.py run` returns `STATUS=handoff`, you are the model executor for that bounded step. Perform the reasoning yourself in the current session using only the returned manifest inputs and contract, write exactly the requested output file, then call `python nel.py run --run-id <id>` again.

Do not delegate a self handoff to another model or LLM API. Do not infer missing evidence from general haematology knowledge.

## Public interface

Use only the root CLI:

```bash
python nel.py init
python nel.py config-check
python nel.py setup ...
python nel.py run ...
python nel.py status ...
python nel.py runs ...
```

Root user configuration is in `config/`, including `config/pipelines/`. Run artefacts are always under `runs/<run-id>/`.
`nel.py` is only the public facade: internally it delegates native self progression to `workflows/terraced_v6/self.py` and non-self execution to `workflows/terraced_v6/step.py`. Do not reproduce either executor's stage logic in the root skill.

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

Never use the old `->project`, system-temp, workflow selector, or workflow-local run interfaces for a new product run.

## Demo and validation modes

Map supported requests to root setup as follows:

```text
nel-demo example N       -> python nel.py setup --mode nel-demo --example N
nel-validate ID          -> python nel.py setup --mode nel-validate --case-id ID
nel-validate-function ID -> python nel.py setup --mode nel-validate-function --case-id ID
nel-validate-brief ID    -> python nel.py setup --mode nel-validate-brief --case-id ID
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

## Legacy workflows

Legacy workflow source may exist in development checkouts, but it is not part of the supported product path. Do not route a user request to `legacy-v1`, `diagnosis-first-v1`, or terraced-v1 through terraced-v5.
