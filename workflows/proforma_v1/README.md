# Proforma v1

Proforma v1 is an experimental NGS Evidence Layer reporting workflow built around explicit clinical proformas, corpus-grounded evidence review, and a declarative workflow definition.

It can be run directly against LM Studio or OpenRouter with `step.py`, or through the current-session model with `self.py`. The shipped workflow definition is `workflow/default.yaml`.

## Quick start

Run commands from the repository root.

### LM Studio

1. Open LM Studio, load the model configured in `workflows/proforma_v1/pipelines/lmstudio.yaml`, and start the OpenAI-compatible local server.
2. Check the pipeline configuration:

```bash
python workflows/proforma_v1/step.py pipeline-check --pipeline lmstudio
```

3. Prepare a case. For a normal report, save the clinical case as Markdown, for example `case.md`:

```bash
python workflows/proforma_v1/step.py setup \
  --mode ngs-report \
  --case-file case.md \
  --pipeline lmstudio
```

`setup` prints the new work directory. Run it with:

```bash
python workflows/proforma_v1/step.py run \
  --work-dir <printed-work-dir>
```

LM Studio defaults to `http://localhost:1234/v1`. Override this with `NEL_LMSTUDIO_BASE_URL` if required:

```bash
export NEL_LMSTUDIO_BASE_URL='http://localhost:1234/v1'
```

### OpenRouter

Export an OpenRouter API key:

```bash
export OPENROUTER_API_KEY='your-openrouter-api-key'
```

Check the pipeline configuration:

```bash
python workflows/proforma_v1/step.py pipeline-check --pipeline openrouter
```

Prepare the case:

```bash
python workflows/proforma_v1/step.py setup \
  --mode ngs-report \
  --case-file case.md \
  --pipeline openrouter
```

Then run the printed work directory:

```bash
python workflows/proforma_v1/step.py run \
  --work-dir <printed-work-dir>
```

The bundled OpenRouter pipeline uses `qwen/qwen3-coder-next` by default. Change model aliases, role assignments, token caps, or provider routing in `workflows/proforma_v1/pipelines/openrouter.yaml`.

### Validation cases

The same provider flow can run bundled validation cases. For example:

```bash
python workflows/proforma_v1/step.py setup \
  --mode nel-validate-brief \
  --case-id 1 \
  --pipeline lmstudio

python workflows/proforma_v1/step.py run \
  --work-dir <printed-work-dir>
```

The dual-pathology validation suite is available only in `proforma_v1`:

```bash
python workflows/proforma_v1/step.py setup \
  --mode nel-validate-dual \
  --case-id 1 \
  --pipeline lmstudio
```

Use `--pipeline openrouter` instead for OpenRouter.

Supported setup modes are:

- `ngs-report`
- `nel-demo`
- `nel-validate`
- `nel-validate-function`
- `nel-validate-brief`
- `nel-validate-dual`

## Provider and model configuration

Provider pipelines live under `workflows/proforma_v1/pipelines/`:

- `lmstudio.yaml` — local OpenAI-compatible LM Studio endpoint;
- `openrouter.yaml` — OpenRouter endpoint and API-key configuration;
- `self.yaml` — current-session model execution.

Non-self pipelines define models once under `model_aliases` and assign workflow roles under `model_roles`. Different roles may use different aliases, temperatures, and output token limits.

For OpenRouter, an alias may also pin provider routing, for example:

```yaml
model_aliases:
  fast: qwen/qwen3-coder-next
  reasoning:
    model: openai/gpt-oss-20b
    provider:
      order: [groq]
      allow_fallbacks: false
```

Pipeline identity is the YAML filename stem. To keep several local configurations, copy an existing pipeline to another filename, edit it, and select that pipeline during setup.

## Settings

The default workflow settings are in:

```text
workflows/proforma_v1/settings.json.template
```

To maintain local workflow settings, copy it once to the gitignored working file:

```bash
cp workflows/proforma_v1/settings.json.template \
   workflows/proforma_v1/settings.json
```

`settings.json` controls retry budgets, diagnostic evidence pools, downstream evidence domains, reportability, prompts, card rendering, and the default pipeline. If the working file is absent, proforma v1 uses `settings.json.template`.

After changing the shipped settings template or shipped pipeline defaults as a developer, validate them with:

```bash
python workflows/proforma_v1/devel_sync.py --check
```

Proforma v1 is not currently the promoted root workflow, so its development defaults are kept separate from root `config/`.

## Workflow

The shipped workflow is:

```text
workflows/proforma_v1/workflow/default.yaml
```

At a high level it performs:

1. structured case extraction and deterministic NGS normalization;
2. WHO5 diagnosis and routing review;
3. ICC and secondary diagnostic assessment;
4. prognosis, treatment, biomarker/MRD, and germline proformas;
5. literature evidence assignment, audit, and conditional adjudication;
6. deterministic report-block construction;
7. final report writing and validation.

The workflow YAML defines logical operations, dependencies, prompts, schemas, registered deterministic transforms/checks, evidence policy, and native-self batching. `step.py` executes the same logical workflow through an external provider; `self.py` executes it through the current session model.

To check the shipped workflow definition:

```bash
python workflows/proforma_v1/step.py workflow-check
```

To experiment with a copied workflow definition, pass it explicitly during setup and run:

```bash
python workflows/proforma_v1/step.py setup \
  --mode ngs-report \
  --case-file case.md \
  --pipeline lmstudio \
  --workflow workflow/my_experiment.yaml

python workflows/proforma_v1/step.py run \
  --work-dir <printed-work-dir> \
  --workflow workflow/my_experiment.yaml
```

See `workflow/README.md` for workflow-authoring examples and `DEVEL.md` for implementation details and the YAML term reference.

## Evidence handling

Clinical owner steps work from bounded evidence cards supplied by the corpus. Downstream evidence review checks the selected support and can attempt bounded evidence rescue when a reportable proposition remains unsupported.

WHO5 routing changes are subject to a stricter blocking evidence gate because they can alter downstream disease-specific retrieval. Unsupported routing changes do not silently become authoritative.

Evidence disagreements are retained through audit/adjudication rather than being hidden by the final writer. The final prose step receives evidence-resolved report blocks and is not intended to change the accepted clinical conclusions.

## Outputs

Each run is stored under:

```text
workflows/proforma_v1/runs/<run-name>/
```

Important outputs include:

- `report-final.md` — final clinical report;
- `report-final.json` — structured final report and run metadata;
- `logs/workflow.log` — workflow trace;
- `logs/model-usage.json` — provider-call timing and token usage for non-self pipelines;
- `logs/transforms.yaml` — deterministic transformations applied during the run;
- `logs/semantic_dissent.yaml` — complete machine-readable semantic dissent ledger;
- `dissent.md` — human-readable statement lifecycles showing origin, review/adjudication stages, and `Kept` / `Revised` / `Abandoned` / `Unresolved` outcomes;
- validation ZIP bundles when using validation modes.

Run state freezes the selected workflow definition and associated assets. Resuming a run is refused if its bound workflow definition has changed, protecting reproducibility.

If `step.py run` is called without `--work-dir`, it uses the most recent prepared proforma-v1 run directory. Supplying the printed work directory explicitly is safer when several runs are active.

## Native self execution

For current-session model execution, use `self.py` instead of an external provider:

```bash
python workflows/proforma_v1/self.py setup \
  --mode nel-validate-dual \
  --case-id 1
```

Follow the handoff sequence described in `SKILL.md`. Native self deliberately does not estimate or log session-model token usage.

## Failure policy

Structured model outputs must pass parsing, schema validation, and registered deterministic checks before they commit. Invalid artifacts are returned to the owning model operation for bounded repair.

Literature support is audited separately from output syntax. Unsupported reportable propositions may be rescued with eligible evidence, adjudicated when necessary, or suppressed according to the workflow's evidence policy. Primary diagnostic routing receives stricter handling because an unsupported routing change could contaminate downstream retrieval.
