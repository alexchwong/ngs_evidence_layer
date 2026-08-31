# Proforma v1

`proforma-v1` is the canonical NGS Evidence Layer reporting workflow. End users should run it through the repository-root `nel.py` facade and root `config/`; workflow-local executors and assets are implementation/developer interfaces.

## Quick start

Run commands from the repository root.

### LM Studio

1. Open LM Studio, load the model configured in `config/pipelines/lmstudio.yaml`, and start the OpenAI-compatible local server.
2. Check the canonical configuration:

```bash
python nel.py config-check --pipeline lmstudio
```

3. Prepare and run a case:

```bash
python nel.py setup \
  --mode ngs-report \
  --case case.md \
  --pipeline lmstudio \
  --run-id my-case

python nel.py run --run-id my-case
```

LM Studio defaults to `http://localhost:1234/v1`. Override this with `NEL_LMSTUDIO_BASE_URL` if required.

### OpenRouter

Export an OpenRouter API key, check the configuration, then set up and run the case:

```bash
export OPENROUTER_API_KEY='your-openrouter-api-key'
python nel.py config-check --pipeline openrouter
python nel.py setup \
  --mode ngs-report \
  --case case.md \
  --pipeline openrouter \
  --run-id my-case
python nel.py run --run-id my-case
```

The bundled OpenRouter pipeline uses `qwen/qwen3-coder-next` by default. Change model aliases, role assignments, token caps, or provider routing in `config/pipelines/openrouter.yaml`.

## Validation modes

Canonical root setup supports:

- `ngs-report`
- `nel-demo`
- `nel-validate`
- `nel-validate-function`
- `nel-validate-brief`
- `nel-validate-dual`

For example:

```bash
python nel.py setup --mode nel-validate-brief --case-id 1 --pipeline lmstudio --run-id brief-1
python nel.py run --run-id brief-1

python nel.py setup --mode nel-validate-dual --case-id 1 --pipeline lmstudio --run-id dual-1
python nel.py run --run-id dual-1
```

## Canonical configuration ownership

Root configuration belongs to `proforma-v1`:

- `config/settings.json` — user working settings;
- `config/settings.json.template` — shipped canonical settings template;
- `config/pipelines/*.yaml` — shipped/user canonical provider pipelines;
- `config/ngs-panel-scope.md` — shared assay scope;
- `config/cul/` — shared corpus user-layer profiles.

The workflow-local `settings.json.template` and `pipelines/*.yaml` are the source defaults used by `devel_sync.py`; they are not the normal end-user configuration surface.

After changing shipped workflow defaults as a developer, synchronize and verify root defaults:

```bash
python workflows/proforma_v1/devel_sync.py
python workflows/proforma_v1/devel_sync.py --check
```

The sync never overwrites user-owned `config/settings.json` or deletes custom root pipeline files.

## Workflow

The shipped declarative workflow is:

```text
workflows/proforma_v1/workflow/default.yaml
```

At a high level it performs:

1. structured case extraction and deterministic NGS normalization;
2. WHO5 diagnosis and routing review;
3. ICC and concurrent-pathology assessment;
4. prognosis, treatment, biomarker/MRD, and germline proformas;
5. literature evidence assignment, audit, and conditional adjudication;
6. deterministic report-block construction;
7. final report writing and validation.

The workflow YAML defines logical operations, dependencies, prompts, schemas, registered deterministic transforms/checks, evidence policy, and native-self batching. `step.py` executes the same logical workflow through an external provider; `self.py` executes it through the current session model.

To check or experiment with workflow internals as a developer:

```bash
python workflows/proforma_v1/step.py workflow-check
python workflows/proforma_v1/step.py setup \
  --mode ngs-report \
  --case-file case.md \
  --pipeline lmstudio \
  --workflow workflow/my_experiment.yaml
```

These direct workflow-local commands are developer interfaces. Product runs should use root `nel.py` so configuration and run freezing follow the canonical facade contract.

See `workflow/README.md` for workflow-authoring examples and `DEVEL.md` for implementation details and the YAML term reference.

## Evidence handling

Clinical owner steps work from bounded evidence cards supplied by the corpus. Downstream evidence review checks selected support and can attempt bounded evidence rescue when a reportable proposition remains unsupported.

WHO5 routing changes are subject to a stricter blocking evidence gate because they can alter downstream disease-specific retrieval. Unsupported routing changes do not silently become authoritative.

Evidence disagreements are retained through audit/adjudication rather than being hidden by the final writer. The final prose step receives evidence-resolved report blocks and is not intended to change accepted clinical conclusions.

## Outputs

Canonical product runs are stored under:

```text
runs/<run-id>/
```

Important outputs include:

- `report-final.md` — final clinical report;
- `report-final.json` — structured final report and run metadata;
- `logs/workflow.log` — workflow trace;
- `logs/model-usage.json` — provider-call timing, token usage, and provider-reported cost for non-self pipelines;
- `logs/transforms.yaml` — deterministic transformations applied during the run;
- `logs/semantic_dissent.yaml` — complete machine-readable semantic dissent ledger;
- `dissent.md` — human-readable statement lifecycles and adjudication outcomes;
- validation ZIP bundles when using validation modes.

Each root run freezes the selected workflow, settings, pipeline, panel scope, corpus/CUL provenance, and workflow identity. Resume with `python nel.py run --run-id <id>`; the run manifest selects the correct executor.

For OpenRouter, each physical provider call retains OpenRouter's returned cost and generation ID when supplied. Run cost is derived from that ledger and printed at completion; NEL does not estimate cost from a local pricing table. Providers that do not return monetary usage keep token accounting but have no fabricated cost.

## Native self execution

For skill/session-model operation, root `nel.py` remains the facade. When `python nel.py run --run-id <id>` returns `STATUS=handoff`, follow the bounded manifest in the root `SKILL.md`, write the requested output, and invoke the same root command again.

`workflows/proforma_v1/self.py` is the implementation adapter behind that facade. Direct invocation is reserved for development/debugging. Native self deliberately does not estimate or log session-model token usage.

## Failure policy

Structured model outputs must pass parsing, schema validation, and registered deterministic checks before they commit. Invalid artifacts are returned to the owning model operation for bounded repair.

Literature support is audited separately from output syntax. Unsupported reportable propositions may be rescued with eligible evidence, adjudicated when necessary, or suppressed according to the workflow's evidence policy. Primary diagnostic routing receives stricter handling because an unsupported routing change could contaminate downstream retrieval.
