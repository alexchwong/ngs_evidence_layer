# NGS Evidence Layer

A corpus-grounded command-line tool for myeloid NGS interpretation.

NEL combines a supplied clinical case with the bundled evidence corpus and explicit reporting rules to produce a concise, citable report. It does not fill evidence gaps from general model knowledge. The canonical product workflow is `proforma-v1`, exposed through the root `nel.py` CLI. `terraced-v6` remains available only as a legacy/reproducibility workflow.

## Contents

- [Quick start](#quick-start)
- [Requirements](#requirements)
- [Choose a model provider](#choose-a-model-provider)
- [Configure NEL](#configure-nel)
- [Run a clinical case](#run-a-clinical-case)
- [Inspect and resume runs](#inspect-and-resume-runs)
- [Proforma-v1 vs terraced-v6](#proforma-v1-vs-terraced-v6)
- [Legacy terraced-v6](#legacy-terraced-v6)
- [Demo and validation modes](#demo-and-validation-modes)
- [CLI reference](#cli-reference)
- [Using the release as a skill](#using-the-release-as-a-skill)
- [Report behavior and boundaries](#report-behavior-and-boundaries)
- [Documentation](#documentation)

## Quick start

Run commands from the repository root. For a local LM Studio workflow:

```bash
python -m venv .env
source .env/bin/activate
python -m pip install -r requirements.txt

# Start LM Studio's OpenAI-compatible server first.
python nel.py config-check --pipeline lmstudio
python nel.py setup --mode ngs-report --case case.md --pipeline lmstudio --run-id my-case
python nel.py run --run-id my-case
```

The completed report is written to:

```text
runs/my-case/report-final.md
```

For OpenRouter, export an API key and substitute `openrouter` for `lmstudio`:

```bash
export OPENROUTER_API_KEY='your-openrouter-api-key'
python nel.py config-check --pipeline openrouter
python nel.py setup --mode ngs-report --case case.md --pipeline openrouter --run-id my-case
python nel.py run --run-id my-case
```

`proforma-v1` is always used for normal root commands. Use `--legacy` only when you deliberately need the older `terraced-v6` workflow.

## Requirements

- Python 3.10 or later
- One of these model providers:
  - [LM Studio](https://lmstudio.ai/) running locally; or
  - [OpenRouter](https://openrouter.ai/) with an API key

Create the repository environment and install the Python dependencies:

```bash
python -m venv .env
source .env/bin/activate
python -m pip install -r requirements.txt
```

The remaining examples assume the environment is activated and commands are run from the repository root.

## Choose a model provider

### LM Studio

1. Install and open LM Studio.
2. Download and load the model configured in `config/pipelines/lmstudio.yaml`. The bundled configuration defines `qwen3-coder-next` once under `model_aliases` and assigns every model role to that alias.
3. Start LM Studio's local OpenAI-compatible server. NEL connects to `http://localhost:1234/v1` by default.
4. Check the NEL configuration and connection settings:

   ```bash
   python nel.py config-check --pipeline lmstudio
   ```

To use another model, edit or add an entry under `model_aliases`, then point the desired entries under `model_roles` at that alias. To use a different server URL, either edit `base_url` in that file or set `NEL_LMSTUDIO_BASE_URL`:

```bash
export NEL_LMSTUDIO_BASE_URL='http://localhost:1234/v1'
```

LM Studio does not require an API key by default. If your server does, set the environment variable named by `api_key_env` in `config/pipelines/lmstudio.yaml`.

### OpenRouter

1. Create an OpenRouter API key.
2. Export it in the shell that will run NEL. **OpenRouter will not work unless `OPENROUTER_API_KEY` is set:**

   ```bash
   export OPENROUTER_API_KEY='your-openrouter-api-key'
   ```

3. Check the NEL configuration:

   ```bash
   python nel.py config-check --pipeline openrouter
   ```

The bundled configuration uses `qwen/qwen3-coder-next`. Define models once under `model_aliases`, then assign each entry under `model_roles` to an alias. An alias may be a plain model ID or an object with OpenRouter provider routing, for example:

```yaml
model_aliases:
  fast: qwen/qwen3-coder-next
  reasoning:
    model: openai/gpt-oss-20b
    provider:
      order: [groq]
      allow_fallbacks: false

model_roles:
  structure:
    model: fast
    temperature: 0.0
    max_tokens: 16384
  diagnosis:
    model: reasoning
    temperature: 0.0
    max_tokens: 65536
```

The provider-routing block is passed through as OpenRouter's request-body `provider` object. Supported routing fields are `order`, `only`, `ignore`, `allow_fallbacks`, and `require_parameters`. The default endpoint is `https://openrouter.ai/api/v1`; set `NEL_OPENROUTER_BASE_URL` only if you need to override it.

Environment variables apply only to the current shell unless added to your shell profile. Never commit an API key to `config/pipelines/openrouter.yaml`, `config/settings.json`, or any other repository file.

## Configure NEL

Create the working settings file once:

```bash
python nel.py init
```

`nel.py setup` and `nel.py config-check` also perform this initialization automatically if `config/settings.json` is missing. The working file is copied from `config/settings.json.template` and is never silently overwritten.

Review these user-editable files before running a case. Root workflow settings and pipeline defaults belong exclusively to canonical `proforma-v1`.

- `config/settings.json` — workflow behavior and default pipeline name;
- `config/ngs-panel-scope.md` — genes assayed by the NGS panel;
- `config/pipelines/lmstudio.yaml` — local LM Studio endpoint, model aliases, role assignments, and token caps;
- `config/pipelines/openrouter.yaml` — OpenRouter endpoint, model aliases, role assignments, provider routing, and token caps.

A pipeline's name is its YAML filename without `.yaml`; there is no separate `pipeline.id`. To keep several configurations for the same provider, copy a default YAML to a new filename and edit that copy, for example:

```bash
cp config/pipelines/lmstudio.yaml config/pipelines/lmstudio-macpro.yaml
cp config/pipelines/openrouter.yaml config/pipelines/openrouter-cheap.yaml
python nel.py config-check --pipeline lmstudio-macpro
```

Set `pipeline` in `config/settings.json` to the filename stem you want as the default, or select any configuration for one run with `--pipeline <name>`.

The bundled settings may name `self` as the default pipeline because that pipeline is used when the release is operated as a `SKILL.md` skill. Human CLI users will usually select an LM Studio or OpenRouter configuration.

Validate the selected configuration before setup:

```bash
python nel.py config-check --pipeline lmstudio
# or
python nel.py config-check --pipeline openrouter
```

### Optional corpus user layer

NEL ships `config/cul/default.json` as the default retrieval-scope profile. Create or inspect
custom profiles with `python scripts/cul.py`, then select one at setup with `--cul <name>`.
The resolved profile and digest are frozen into the run configuration. See
[`docs/cul.md`](docs/cul.md) for scope, amendments, staleness, disclosure, and the standalone editor.

## Run a clinical case

Save the clinical case as Markdown, for example `case.md`. Preserve all information required for interpretation in that file.

Create a run with LM Studio:

```bash
python nel.py setup \
  --mode ngs-report \
  --case case.md \
  --pipeline lmstudio \
  --run-id my-case-001
```

Or create it with OpenRouter after setting `OPENROUTER_API_KEY`:

```bash
export OPENROUTER_API_KEY='your-openrouter-api-key'
python nel.py setup \
  --mode ngs-report \
  --case case.md \
  --pipeline openrouter \
  --run-id my-case-001
```

Run the prepared case:

```bash
python nel.py run --run-id my-case-001
```

For LM Studio and OpenRouter, this executes the model-backed workflow. When it completes, the final report is written to:

```text
runs/my-case-001/report-final.md
```

Each run contains a frozen `run-config/` snapshot, so resuming it uses the settings, pipeline, panel scope, and provenance captured during setup. Existing run IDs are never overwritten. If `--run-id` is omitted, setup generates a timestamp-based ID.

## Inspect and resume runs

Check one run:

```bash
python nel.py status --run-id my-case-001
```

Continue it:

```bash
python nel.py run --run-id my-case-001
```

If `--run-id` is omitted, `run` and `status` use the latest prepared run:

```bash
python nel.py status
python nel.py run
```

Survey all runs or only incomplete runs:

```bash
python nel.py runs
python nel.py runs --incomplete
```

All run data is stored under the gitignored `runs/<run-id>/` directory.


## Proforma-v1 vs terraced-v6

`proforma-v1` is the supported product workflow. `terraced-v6` is retained so older runs and deliberate legacy comparisons remain reproducible.

| Area | `proforma-v1` | `terraced-v6` |
| --- | --- | --- |
| Status | Canonical workflow for new runs | Legacy/reproducibility workflow |
| Root CLI | Default for normal `nel.py` commands | Selected explicitly with `--legacy` during setup/configuration |
| Configuration | Root `config/settings.json` and `config/pipelines/` | Workflow-local `workflows/terraced_v6/settings.json` and `pipelines/` |
| Workflow definition | Declarative `workflow/default.yaml` with registered operations, dependencies and evidence policies | Older staged/native executor topology implemented directly in workflow code |
| WHO diagnosis | WHO5 routing changes are evidence-gated before commit; an authoritative WHO reassessment runs when required | Legacy WHO/ICC/second-diagnosis topology retained for reproducibility |
| Concurrent pathology | WHO5 assesses each detected variant; strong signals for another pathology are projected as non-routing concurrent-pathology findings | Legacy staged workflow uses an independent second-diagnosis path |
| Evidence review | Explicit assignment → independent audit → conditional adjudication, including a blocking gate for WHO routing changes | Older evidence-resolution/audit implementation retained |
| Report construction | Evidence-finalized propositions are converted into deterministic report blocks before final prose; provider-backed runs also use a preservation check | Legacy report synthesis/preservation topology retained |
| Workflow evolution | Current validation and reporting changes target this workflow | Receives only fixes needed to keep the legacy path runnable |

For routine clinical reporting, demos and validation, use `proforma-v1`. Use `terraced-v6` only when reproducing a prior result, comparing workflow generations, or maintaining an existing legacy run.

## Legacy terraced-v6

`proforma-v1` is the canonical workflow. `terraced-v6` is retained only for explicit legacy/reproducibility use through the same root facade. Do not place terraced settings or pipelines in root `config/`.

Check the legacy configuration or create a new legacy run with `--legacy`:

```bash
python nel.py config-check --legacy --pipeline lmstudio
python nel.py setup --legacy --mode nel-demo --example 1 --pipeline lmstudio --run-id legacy-demo-1
python nel.py setup --legacy --mode nel-validate-dublin --case-id 1 --pipeline lmstudio --run-id legacy-dublin-1
```

Legacy setup reads `workflows/terraced_v6/settings.json` when present (otherwise its local template) and `workflows/terraced_v6/pipelines/`. To create a workflow-local editable settings file, run `python nel.py init --legacy`. After setup, resume normally with `python nel.py run --run-id <id>`; the frozen run manifest selects the executor, so `--legacy` is not used on `run` or `status`.

## Demo and validation modes

Bundled examples and validation suites use the same CLI. Select either `lmstudio` or `openrouter` explicitly:

```bash
python nel.py setup --mode nel-demo --example 1 --pipeline lmstudio --run-id demo-1
python nel.py setup --mode nel-validate --case-id 1A --pipeline lmstudio --run-id validation-1A
python nel.py setup --mode nel-validate-function --case-id 1A --pipeline lmstudio --run-id function-1A
python nel.py setup --mode nel-validate-brief --case-id 1 --pipeline lmstudio --run-id brief-1
python nel.py setup --mode nel-validate-dual --case-id 1 --pipeline lmstudio --run-id dual-1
python nel.py setup --mode nel-validate-dublin --case-id 1 --pipeline lmstudio --run-id dublin-1
```

Then execute the prepared run:

```bash
python nel.py run --run-id <run-id>
```

See [`docs/validation.md`](docs/validation.md) for validation-suite case IDs.

## CLI reference

Display the available commands and command-specific options:

```bash
python nel.py --help
python nel.py init --help
python nel.py setup --help
python nel.py run --help
```

The public commands are:

- `setup` — create a new run;
- `run` — execute or resume a run;
- `status` — inspect one run's artifact-derived status;
- `runs` — survey existing runs;
- `config-check` — validate configuration and corpus integrity;
- `pipelines` — inspect installed pipeline definitions;
- `ui` — serve the local browser interface.

## Browser interface

An optional browser interface drives the same `nel.py` commands from a local web page. It runs on
this machine only:

```bash
python nel.py ui
```

The terminal prints an address carrying a one-time session token; open that address. The interface
binds `127.0.0.1` and cannot be exposed to other machines. Use `--port` to move it and
`--no-browser` to suppress the automatic browser launch.

What it does:

- prepares and runs free-text cases, the `nel-demo` examples and the `nel-validate*` suites;
- edits provider profiles: endpoint, model options, OpenRouter provider routing, and the assignment
  of options to workflow roles;
- accepts a provider API key, held in server memory for the life of the process and injected into
  each `nel.py` child. **Keys are never written to disk and are lost when the server stops.** Never
  put a key in a pipeline YAML file;
- shows the live console, the terraced stage rail, token and cost accounting, the rendered report,
  and every intermediate file a run produced;
- deletes a run, or archives it — archiving removes `case.md`, `intermediates/` and `model_steps/`
  and keeps the report, logs and run configuration.

Runs whose provider is a loopback address, such as LM Studio, run one at a time. Runs against a
remote provider may run concurrently.

The profiles shipped with the repository — `self`, `lmstudio` and `openrouter` — are read-only in
the interface; save your changes under a new name. `self` is hidden, because its handoff protocol
needs a session model and cannot be driven unattended.

The interface writes only to `runs/`, `.nel-ui/` and `config/pipelines/`, and it is not part of the
release skill archive.

## Using the release as a skill

The `self` pipeline is reserved for applications and agents that execute the release through [`SKILL.md`](SKILL.md). It returns bounded model handoffs for the current chat session instead of calling LM Studio or OpenRouter. End users running `nel.py` directly should use `lmstudio` or `openrouter` and do not need to operate the self-handoff protocol.

To use a release ZIP as a chat skill, upload it through your application's skill or project-source mechanism and instruct the application to follow `SKILL.md`.

## Report behavior and boundaries

`proforma-v1` separates clinical interpretation, evidence support, deterministic transformations and final prose so that reportable conclusions can be traced back through the run artifacts.

### Report behavior

At a high level, the canonical workflow:

1. **Structures the supplied case.** It extracts case facts and variants into a validated structured artifact. For a complete NGS result, Python also materializes assayed panel genes with no detected variant from `config/ngs-panel-scope.md`; these negatives are not invented by the model.
2. **Establishes the primary diagnosis.** WHO5 is assessed first. If that assessment would change downstream WHO routing, the change is held behind a blocking evidence assignment, audit and adjudication gate before it can commit. A second authoritative WHO5 assessment runs when the workflow determines reconsideration is required. ICC is assessed separately and retained alongside WHO5.
3. **Separates concurrent-pathology signals from primary routing.** WHO5 classifies detected variants for their diagnostic significance. A strong molecular signal for a distinct pathology can become a `concurrent_pathology` report candidate, but it does not itself change the primary WHO/ICC disease used for downstream retrieval and does not by itself prove a second neoplasm.
4. **Runs domain-specific interpretation.** Prognosis, treatment, biomarker/MRD and germline implications are completed against the finalized diagnosis and bounded corpus evidence. Reportability settings determine which positive, negative or uncertain categories are eligible for the final report.
5. **Resolves literature support.** Candidate reportable propositions pass through evidence assignment and an independent evidence audit. Failed audits can trigger bounded reassignment; remaining disagreements proceed to adjudication and are retained in the dissent trail rather than being silently erased.
6. **Builds the report deterministically before prose synthesis.** Accepted evidence is finalized, report propositions are normalized/aggregated where registered transforms require it, and deterministic report blocks are constructed before the report writer sees them.
7. **Writes and validates the final report.** Provider-backed runs perform a report-preservation check before deterministic finalization. Citations are rendered from accepted corpus evidence, with Vancouver-style numbering in order of first citation. Native `self` execution uses the same clinical workflow contract but does not run the separate preservation-model step.

Useful run artifacts include `report-final.md`, `report-final.json`, `dissent.md`, `logs/workflow.log`, `logs/transforms.yaml`, `logs/semantic_dissent.yaml`, and the structured intermediates under `runs/<run-id>/`.

### Boundaries

- **Corpus-grounded only:** NEL does not fill evidence gaps from general model memory. A proposition unsupported by eligible corpus evidence can be suppressed or retained as dissent according to workflow policy rather than being rescued from outside knowledge.
- **No live clinical lookup during interpretation:** NEL does not query current drug approvals, guidelines, trial registries or other external databases while producing the report. The bundled corpus therefore defines the evidence ceiling for a run.
- **Case facts remain authoritative inputs:** the workflow may normalize and structure supplied facts, but it must not create missing clinical, morphological, cytogenetic or molecular observations.
- **Concurrent pathology is a signal, not an automatic second diagnosis:** these findings are reported as warranting investigation/clinicopathological correlation unless the deterministic report block explicitly supports a stronger conclusion.
- **WHO routing has a higher evidence bar:** unsupported molecular/cytogenetic changes that would alter downstream WHO retrieval are not silently committed.
- **Reporting rules are distinct from evidence:** `config/settings.json` controls reportability and workflow behavior; the evidence corpus controls what literature support is available. Changing a reportability switch does not create supporting evidence.
- **Runs are reproducible snapshots:** setup freezes the selected workflow, settings, pipeline, panel scope and corpus/CUL provenance into `run-config/`. Resuming a run uses that frozen identity rather than whichever defaults exist later.
- **`proforma-v1` is the supported product interface:** other workflows are development or legacy implementations. `terraced-v6` is supported only through the explicit legacy path described below.

## Documentation

- [`docs/corpus.md`](docs/corpus.md) — publications in the current evidence corpus;
- [`docs/cul.md`](docs/cul.md) — optional corpus user layer profiles and editor;
- [`docs/validation.md`](docs/validation.md) — bundled validation suites and case IDs;
- [`SKILL.md`](SKILL.md) — instructions for skill-capable applications and agents;
- [`NEWS.md`](NEWS.md) — changelog.