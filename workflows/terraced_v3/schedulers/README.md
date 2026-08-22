# Terraced-v3 declarative scheduler developer guide

Schedulers are YAML instruction sets interpreted by one core Python orchestrator (`scheduler_engine.py`). Do not add scheduler-specific Python runners. Python owns legal primitives, validators, CMC derivation, evidence trust and artifact handling; scheduler YAML owns model-call topology and information flow **within one phase**.

## Three invariant scheduler phases

```text
diagnosis scheduler
  INPUT  fixed diagnosis context/retrieval services
  OUTPUT {icc, who5, routing}
        ↓
core validates/finalises WHO5-derived CMC routing
        ↓
PTBG scheduler
  INPUT  fixed case + settled WHO5/final CMC + domain retrieval
  OUTPUT {prognosis, treatment, biomarker, germline}
        ↓
core fact/reason ↔ card alignment
        ↓
summarization scheduler
  INPUT  fixed locked cited fact ledger
  OUTPUT {summary: {sentences: [...]}}
```

A scheduler may change how it reaches the output, but cannot change the phase interface.

## Directory structure

```text
schedulers/
├── README.md
├── scheduler_schema.yaml
├── common/
│   └── prompts/
├── diagnosis/
│   ├── default-diagnosis/
│   │   ├── scheduler.yaml
│   │   └── prompts/
│   └── minimal-diagnosis/
│       ├── scheduler.yaml
│       └── prompts/
├── ptbg/
│   ├── domain/
│   ├── evidence-first/
│   ├── variant-centric/
│   ├── global-ledger/
│   └── adaptive-microtask/
└── summarization/
    ├── default-summarization/
    │   ├── scheduler.yaml
    │   └── prompts/
    └── minimal-summarization/
        ├── scheduler.yaml
        └── prompts/
```

Each scheduler folder should normally contain only `scheduler.yaml` and `prompts/`.

## Scheduler metadata and outputs

Every scheduler declares its phase:

```yaml
scheduler:
  id: domain
  phase: ptbg
  version: 1
  description: One model task per downstream domain.
```

Canonical outputs are fixed by phase:

```yaml
# diagnosis
outputs:
  icc: steps.icc
  who5: steps.who5.who5
  routing: steps.who5.routing

# PTBG
outputs:
  prognosis: steps.publish.prognosis
  treatment: steps.publish.treatment
  biomarker: steps.publish.biomarker
  germline: steps.publish.germline

# summarization
outputs:
  summary: steps.synthesize.summary
```

The engine rejects a scheduler whose output keys differ from its phase contract.

## Model steps

A normal model step declares every runtime input before using it:

```yaml
- id: adjudicate
  kind: model
  foreach: domains
  inputs:
    case: core.case
    diagnoses: core.diagnoses
    scope: core.specs[$item]
    evidence: evidence[$item]
  prompt:
    template: prompts/adjudicate.md
    inject:
      case: {input: case, render: json}
      diagnoses: {input: diagnoses, render: yaml}
      scope: {input: scope, render: yaml}
      evidence: {input: evidence, render: text}
  output:
    format: yaml
    validator: domain
    contract: canonical_domain
```

`foreach` currently supports `domains`, `variants`, and list/dict outputs of earlier steps.

## Prompt templates

Prompt templates are plain Markdown. Runtime content appears only through named slots:

```markdown
{{common_rules}}

# Case
{{case}}

# Previous state
{{previous_state}}
```

Every slot must have exactly one `prompt.inject` declaration. Missing or unused declarations fail `scheduler-check` before a model call.

### Injecting one prompt into another

Use a static prompt fragment:

```yaml
prompt:
  template: prompts/adjudicate.md
  inject:
    common_rules:
      prompt: ../../common/prompts/domain_task.md
```

For a domain-dependent fragment:

```yaml
domain_contract:
  prompt_select:
    prognosis: ../../common/prompts/prognosis_contract.md
    treatment: ../../common/prompts/treatment_contract.md
    biomarker: ../../common/prompts/biomarker_contract.md
    germline: ../../common/prompts/germline_contract.md
```

Do not use Jinja includes or Python string concatenation.

### Injecting an earlier model output

First declare it as an input:

```yaml
inputs:
  previous_state: steps.initial
```

then inject it:

```yaml
prompt:
  template: prompts/review.md
  inject:
    previous_state: {input: previous_state, render: yaml}
```

Static prompt fragments (`prompt:`) and runtime outputs (`input:`) are intentionally distinct.

## Diagnosis schedulers

Diagnosis schedulers have access to core case/panel/WHO5 vocabulary inputs and diagnosis retrieval. CMC remains a core invariant: schedulers never authoritatively set CMC. Core derives it from validated WHO5 `schema_disease` values.

`default-diagnosis` uses the registered `diagnosis_loop` kind. Its YAML supplies the main/reconsider/review instructions and maximum-pass source; the engine supplies safe loop semantics: retrieve cumulative old+new CMC evidence, derive CMC after every WHO5 pass, detect CMC transitions, require reconsideration and adversarial confirmation, and reject oscillation.

`minimal-diagnosis` is a deliberately small developer example: blind ICC + one WHO5 pass + deterministic CMC publication. It demonstrates the interface, not the recommended diagnostic safety depth.

## PTBG schedulers

The five PTBG schedulers differ only in how they create the same four canonical states:

- `domain`
- `evidence-first`
- `variant-centric`
- `global-ledger`
- `adaptive-microtask`

The existing common prompt fragments under `common/prompts/` define the canonical clinical contracts.

## Summarization schedulers

Input is the locked cited fact ledger. A summarization scheduler may change drafting/review topology but may not invent clinical facts or alter citation trust.

The canonical output is:

```yaml
summary:
  sentences:
    - sentence_id: prognosis-1
      domain: prognosis
      sentence: "..."
      fact_ids: [prognosis-V1-DX1]
      card_tags: ["[card:abcdefabcdef]"]
```

`card_tags` are not freely chosen by the summarizer: core validation requires them to equal the citations inherited from the paired `fact_ids`.

`default-summarization` reproduces the current two-step behaviour: draft prose → semantic sentence/fact alignment, with one complete rewrite if facts are omitted. `minimal-summarization` shows a single-call alternative that emits sentence/fact pairs directly.

After any summarization scheduler completes, core deterministically resolves each paired card tag to its drawn card interpretation and writes `sentence-card-interpretations.yaml`.

## Deterministic operations and special loop kinds

Normal deterministic work uses registered `kind: operation` primitives. The schema currently also has two bounded core loop kinds:

- `diagnosis_loop` — WHO5/CMC stabilisation semantics;
- `summarization_loop` — draft/alignment coverage loop.

These are core-controlled because they enforce safety/integrity invariants. Scheduler YAML controls their prompts, instructions and bounded configuration, not arbitrary code.

Do not add Python expressions, lambdas, arbitrary conditionals or executable templates to YAML. If a genuinely reusable deterministic behaviour is missing, add one tested primitive to `scheduler_primitives.py`.

## Developer commands

```bash
python workflows/terraced_v3/step.py schedulers
python workflows/terraced_v3/step.py schedulers --phase diagnosis
python workflows/terraced_v3/step.py scheduler-check --phase ptbg --scheduler evidence-first
python workflows/terraced_v3/step.py scheduler-plan --phase summarization --scheduler default-summarization
```

Always run `scheduler-check` after changing YAML or prompt assets. It checks phase/output contracts, dependency order, registered validators/primitives, prompt existence and prompt-slot declarations.
