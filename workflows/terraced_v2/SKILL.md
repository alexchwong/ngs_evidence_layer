---
name: ngs-evidence-layer-terraced-v2
description: YAML-driven terraced workflow using diagnosis-lab diagnostic state and serial prognosis, treatment, biomarker/MRD, and germline terraces.
---
# NGS evidence layer — terraced-v2

## Scope

Supported modes:

- `ngs-report`
- `nel-demo example <N>`
- `nel-validate <case-id>`
- `nel-validate-function <case-id>`
- `nel-validate-brief <case-id>`

`workflows/terraced_v2/workflow.yaml` is the canonical pipeline definition. `step.py` reads that YAML and dispatches the configured deterministic/model modules. Do not reconstruct or reorder the pipeline from this SKILL file.

The workflow is serial by design for local-model reliability. Diagnosis runs first, followed by germline, prognosis, biomarker/MRD and treatment. Treatment is last because its terraces may consume accepted prognosis, biomarker and germline facts. Report order is independently configured in `workflow.yaml`.

`case.md` is the immutable human-authored source. The first model operation structures it once into `input/case.json`; after that, model stages use `case.json`, not the raw prose. The raw case remains audit-only.

Diagnosis follows the diagnosis-lab state model. WHO5 controls final routing; ICC is comparator-only. At the diagnosis boundary, only CMC, WHO5 diagnosis state and accepted diagnosis facts pass downstream. Diagnostic uncertainties are deliberately shed. Each downstream domain may create its own local uncertainties, but uncertainties never become premises for another domain. Downstream stages cannot mutate diagnosis; a genuine contradiction is recorded as an audit-only `upstream_issue`.

Evidence is category-local. Diagnosis draws diagnosis plus gene-matched germline evidence from fixed case genes, evolving CMC and terrace category at the start of each diagnosis terrace. Germline/prognosis/biomarker/treatment use their corresponding corpus categories with terraced-v1 narrow disease/gene retrieval semantics. Every corpus card receives a deterministic 12-hex run-global identity at initialisation before filtering/retrieval.

## Provider equivalence

The exact same `workflow.yaml`, prompts, deterministic modules, validators, card draws, context boundaries and output contracts are used for all providers:

- `self`
- `lmstudio`
- `ollama`
- `openrouter`

Only the model transport changes. In ChatGPT, always use model profile `self` unless the user explicitly selected another provider.

When a `self` run exits `10`, read only the printed `PROMPT=<path>`, perform that bounded model operation in the current session, write only the exact `OUTPUT=<path>`, then rerun the same `run` command. Do not inspect unrelated repository files to infer hidden inputs.

## Setup

At Step 0 only, prepare the environment if needed:

```bash
python3 -m venv .env
.env/bin/python -m pip install -r requirements.txt
```

Use `.env/bin/python` as `<python>`.

For ChatGPT/session execution use `self` and normally `frontier` grouping. For an interactive `ngs-report`, first write the user-supplied case source **verbatim** to a temporary `case.md`; do not structure, interpret or normalize it yourself. Pass that file to setup. The authoritative copy is then `input/case.md` inside the created work directory.

```bash
# ngs-report
<python> workflows/terraced_v2/step.py setup --mode ngs-report \
  --case-file case.md --model-profile self --terrace-profile frontier --project

# demo
<python> workflows/terraced_v2/step.py setup --mode nel-demo --example <N> \
  --model-profile self --terrace-profile frontier --project

# validation
<python> workflows/terraced_v2/step.py setup --mode nel-validate --case-id <ID> \
  --model-profile self --terrace-profile frontier --project

<python> workflows/terraced_v2/step.py setup --mode nel-validate-function --case-id <ID> \
  --model-profile self --terrace-profile frontier --project

<python> workflows/terraced_v2/step.py setup --mode nel-validate-brief --case-id <ID> \
  --model-profile self --terrace-profile frontier --project
```

Record the first output line as `<work-dir>`. New project runs use readable timestamped directory names rather than random hashes.

## Execute

Run:

```bash
<python> workflows/terraced_v2/step.py run --work-dir <work-dir>
```

For a `self` handoff (exit `10`):

1. read only the printed `PROMPT=<path>`;
2. execute that bounded model task yourself;
3. write only the requested `OUTPUT=<path>`;
4. rerun the same command;
5. repeat until exit `0`.

The runner is resumable: completed model artifacts are deterministically revalidated and reused.

## Direct providers

The provider is a model profile, not a workflow branch:

```bash
<python> workflows/terraced_v2/step.py setup --mode ngs-report --case-file case.md \
  --model-profile lmstudio --terrace-profile balanced --project

<python> workflows/terraced_v2/step.py setup --mode ngs-report --case-file case.md \
  --model-profile ollama --terrace-profile deliberate --project

<python> workflows/terraced_v2/step.py setup --mode ngs-report --case-file case.md \
  --model-profile openrouter --terrace-profile balanced --project
```

Provider endpoints/model IDs are configured in `models.json` (falling back to `models.json.template`) and can be overridden with the corresponding environment variables. OpenRouter requires `OPENROUTER_API_KEY`.

## Important outputs

- `input/case.md` — immutable source case.
- `input/case.json` — canonical shared machine case state.
- `evidence/card-identity-manifest.json` — whole-corpus deterministic identity.
- `diagnosis/FINAL_OUTPUT.yaml` — final paired WHO5/ICC diagnostic state, including diagnosis-local uncertainty.
- `<domain>/FINAL_STATE.yaml` — final facts/uncertainties/upstream review issues for germline, prognosis, biomarker and treatment.
- `<domain>/FINAL_ALIGNED.yaml` — immutable final state with evidence dispositions.
- `report-final.md` — rendered clinical report with resolved references.
- `workflow.log` — complete CLI log; routine validation-pass and low-level render/retrieve chatter is masked from terminal output.
- `terraced-v2-debug.zip` — auditable run bundle.
- validation modes additionally create an external marking package; the workflow does not mark its own report.
