# NGS Evidence Layer

A corpus-grounded command-line tool for myeloid NGS interpretation.

NEL combines a supplied clinical case with the bundled evidence corpus and explicit reporting rules to produce a concise, citable report. It does not fill evidence gaps from general model knowledge. The supported product workflow is `terraced-v6`, exposed through the root `nel.py` CLI.

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
2. Download and load the model configured in `pipelines/lmstudio.yaml`. The bundled configuration uses `qwen3-coder-next` for every model role.
3. Start LM Studio's local OpenAI-compatible server. NEL connects to `http://localhost:1234/v1` by default.
4. Check the NEL configuration and connection settings:

   ```bash
   python nel.py config-check --pipeline lmstudio
   ```

To use another model, edit the model IDs in `pipelines/lmstudio.yaml`. To use a different server URL, either edit `base_url` in that file or set `NEL_LMSTUDIO_BASE_URL`:

```bash
export NEL_LMSTUDIO_BASE_URL='http://localhost:1234/v1'
```

LM Studio does not require an API key by default. If your server does, set the environment variable named by `api_key_env` in `pipelines/lmstudio.yaml`.

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

The bundled configuration uses `qwen/qwen3-coder-next`. Model IDs and request limits can be changed in `pipelines/openrouter.yaml`. The default endpoint is `https://openrouter.ai/api/v1`; set `NEL_OPENROUTER_BASE_URL` only if you need to override it.

Environment variables apply only to the current shell unless added to your shell profile. Never commit an API key to `pipelines/openrouter.yaml`, `config/settings.json`, or any other repository file.

## Configure NEL

Review these user-editable files before running a case:

- `config/settings.json` — workflow behavior and default pipeline;
- `config/ngs-panel-scope.md` — genes assayed by the NGS panel;
- `pipelines/lmstudio.yaml` — local LM Studio endpoint and model bindings;
- `pipelines/openrouter.yaml` — OpenRouter endpoint and model bindings.

The bundled settings may name `self` as the default pipeline because that pipeline is used when the release is operated as a `SKILL.md` skill. `self` is not an end-user CLI provider. CLI users should pass `--pipeline lmstudio` or `--pipeline openrouter`, or change the `pipeline` value in `config/settings.json` to one of those two values.

Validate the selected configuration before setup:

```bash
python nel.py config-check --pipeline lmstudio
# or
python nel.py config-check --pipeline openrouter
```

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

## Demo and validation modes

Bundled examples and validation suites use the same CLI. Select either `lmstudio` or `openrouter` explicitly:

```bash
python nel.py setup --mode nel-demo --example 1 --pipeline lmstudio --run-id demo-1
python nel.py setup --mode nel-validate --case-id 1A --pipeline lmstudio --run-id validation-1A
python nel.py setup --mode nel-validate-function --case-id 1A --pipeline lmstudio --run-id function-1A
python nel.py setup --mode nel-validate-brief --case-id 1 --pipeline lmstudio --run-id brief-1
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
python nel.py setup --help
python nel.py run --help
```

The public commands are:

- `setup` — create a new run;
- `run` — execute or resume a run;
- `status` — inspect one run's artifact-derived status;
- `runs` — survey existing runs;
- `config-check` — validate configuration and corpus integrity;
- `pipelines` — inspect installed pipeline definitions.

## Using the release as a skill

The `self` pipeline is reserved for applications and agents that execute the release through [`SKILL.md`](SKILL.md). It returns bounded model handoffs for the current chat session instead of calling LM Studio or OpenRouter. End users running `nel.py` directly should use `lmstudio` or `openrouter` and do not need to operate the self-handoff protocol.

To use a release ZIP as a chat skill, upload it through your application's skill or project-source mechanism and instruct the application to follow `SKILL.md`.

## Report behavior and boundaries

Terraced-v6:

1. preserves and structures the supplied case;
2. performs WHO5, ICC, and authoritative second-WHO5 diagnostic assessment;
3. evaluates prognosis, treatment, MRD/biomarker, and germline implications;
4. resolves supporting evidence for reportable reasons;
5. independently audits evidence assignments and adjudicates disagreements;
6. constructs deterministic citable report blocks; and
7. synthesizes the final report against the original case context.

The final report uses Vancouver-style citations in square brackets and numbers references in order of first citation.

Important boundaries:

- NEL reports only what the supplied case and bundled corpus support.
- Different publications can coexist in the corpus even when their recommendations differ.
- NEL does not query live approval, drug, guideline, or other external databases during interpretation.
- Evidence absent from the corpus is not supplied from model memory.
- The evidence corpus is distinct from reporting rules and formatting prompts.
- Other directories under `workflows/` are legacy or development code, not supported product interfaces.

## Documentation

- [`docs/corpus.md`](docs/corpus.md) — publications in the current evidence corpus;
- [`docs/validation.md`](docs/validation.md) — bundled validation suites and case IDs;
- [`SKILL.md`](SKILL.md) — instructions for skill-capable applications and agents;
- [`NEWS.md`](NEWS.md) — changelog.