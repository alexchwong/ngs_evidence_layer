# Terraced-v3 declarative scheduler developer guide

A terraced-v3 scheduler is **data, not Python code**. Each scheduler directory contains a `scheduler.yaml` instruction set plus optional prompt templates. One core Python orchestrator (`scheduler_engine.py`) parses the YAML and executes only registered primitives.

The scheduler controls **how downstream clinical synthesis flows**. It may choose task order, batching/iteration, prompt composition, prior-output injection, review terraces and deterministic assembly. It must still finish with the same four canonical outputs: prognosis, treatment, biomarker/MRD and germline.

## Directory structure

```text
workflows/terraced_v3/
├── scheduler_engine.py          # generic YAML orchestrator
├── scheduler_registry.py        # discovers scheduler.yaml directories
├── scheduler_primitives.py      # legal validators/operations/data sources
└── schedulers/
    ├── README.md
    ├── scheduler_schema.yaml
    ├── common/
    │   ├── prompts/
    │   │   ├── domain_task.md
    │   │   ├── prognosis_contract.md
    │   │   ├── treatment_contract.md
    │   │   ├── biomarker_contract.md
    │   │   └── germline_contract.md
    │   └── examples/
    │       └── minimal_scheduler.yaml
    ├── domain/
    │   ├── scheduler.yaml
    │   └── prompts/adjudicate.md
    ├── evidence-first/
    │   ├── scheduler.yaml
    │   └── prompts/
    │       ├── normalize_evidence.md
    │       └── adjudicate.md
    ├── variant-centric/
    │   ├── scheduler.yaml
    │   └── prompts/
    │       ├── variant_review.md
    │       └── germline_clinical_picture.md
    ├── global-ledger/
    │   ├── scheduler.yaml
    │   └── prompts/
    │       ├── initial_ledger.md
    │       └── adversarial_review.md
    └── adaptive-microtask/
        ├── scheduler.yaml
        └── prompts/
            ├── initial_domain.md
            └── review_cell.md
```

Do not add scheduler-specific `.py` files. If a new scheduler needs a deterministic capability that the YAML cannot express, add a reusable, tested primitive to `scheduler_primitives.py`, then reference that primitive from YAML.

## Minimal scheduler YAML

A scheduler has metadata, ordered steps, and explicit canonical outputs:

```yaml
scheduler:
  id: domain
  version: 1
  order: 10
  description: One model task per downstream domain.

steps:
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
        common_rules:
          prompt: ../common/prompts/domain_task.md
        case:
          input: case
          render: json
        diagnoses:
          input: diagnoses
          render: yaml
        scope:
          input: scope
          render: yaml
        evidence:
          input: evidence
          render: text
    output:
      format: yaml
      validator: domain
      contract: canonical_domain

  - id: publish
    kind: operation
    operation: publish_domains
    inputs:
      states: steps.adjudicate

outputs:
  prognosis: steps.publish.prognosis
  treatment: steps.publish.treatment
  biomarker: steps.publish.biomarker
  germline: steps.publish.germline
```

Steps execute top-to-bottom. `depends_on` may document explicit dependencies; a dependency must refer to an earlier step. The engine does not permit forward references.

## Model steps

A model step uses:

```yaml
kind: model
foreach: domains        # optional
inputs: ...
prompt: ...
output: ...
```

Supported iteration sources currently are:

- `domains` — prognosis, treatment, biomarker, germline;
- `variants` — each structured detected variant;
- `steps.<step-id>` — iterate a list created by an earlier deterministic step.

The scheduler engine writes scheduler-specific artifacts under the numbered scheduler intermediate directory and model interactions under the normal numbered `model_steps/` namespace. Resume reuses already-generated step artifacts.

## Inputs and information flow

Every runtime value used by a prompt must first be declared under that step's `inputs`.

Common core inputs include:

```yaml
case: core.case
diagnoses: core.diagnoses
diagnosis_context: core.diagnosis_context
final_cmcs: core.final_cmcs
scope: core.specs[$item]
variants: core.variants
```

Evidence is requested through the core retrieval service:

```yaml
evidence: evidence[$item]          # current domain
evidence: evidence[$item.domain]   # domain stored in an iterated cell
evidence: evidence.all             # all four downstream evidence bundles
evidence: evidence.germline        # one named domain
```

Earlier scheduler output is explicit:

```yaml
normalized_evidence: steps.normalize[$item]
initial_ledger: steps.initial
reviews: steps.review
```

This is the main audit principle: **the YAML should make it possible to follow every model input back to core state, evidence retrieval, static prompt assets, or a named previous step.**

## Prompt templates

Prompt templates are plain Markdown with named slots:

```markdown
{{common_rules}}

# Case
```json
{{case}}
```

# Previous state
```yaml
{{previous_state}}
```
```

Every `{{slot}}` must have exactly one declaration in `prompt.inject`. An undeclared slot or an unused injection declaration is a scheduler compile error.

Prompt templates do not fetch data and do not contain executable workflow logic. Put branching/ordering in `scheduler.yaml`, not Markdown.

## Injecting a prompt fragment into another prompt

Static reusable instructions use `prompt:`:

```yaml
prompt:
  template: prompts/adjudicate.md
  inject:
    common_rules:
      prompt: ../common/prompts/domain_task.md
```

The template contains:

```markdown
{{common_rules}}
```

Domain-specific fragments can be selected declaratively for a `foreach: domains` task:

```yaml
domain_contract:
  prompt_select:
    prognosis: ../common/prompts/prognosis_contract.md
    treatment: ../common/prompts/treatment_contract.md
    biomarker: ../common/prompts/biomarker_contract.md
    germline: ../common/prompts/germline_contract.md
```

This is the preferred way to compose prompts. Do not concatenate prompt files in scheduler-specific Python.

## Injecting an earlier model output into a later prompt

Declare the earlier step as an input:

```yaml
inputs:
  previous_state: steps.initial
```

Then inject it:

```yaml
prompt:
  template: prompts/review.md
  inject:
    previous_state:
      input: previous_state
      render: yaml
```

This makes the dependency visible and preserves a clean distinction:

- `prompt:` source = static instruction asset;
- `input:` source = runtime information or earlier model output.

## Deterministic operation steps

A non-model step uses a registered operation:

```yaml
- id: apply_patch
  kind: operation
  operation: apply_domain_patch
  inputs:
    initial: steps.initial
    patch: steps.review
```

Current primitives are listed in `scheduler_schema.yaml`. They cover the five shipped strategies: variant-output assembly, domain-patch application, high-impact-cell selection, adaptive review application and canonical publication.

Do not embed Python, Jinja conditionals, lambdas or arbitrary expressions in YAML. If a new generic operation is genuinely needed, implement it as a core primitive with deterministic tests.

## Output contracts

Model outputs always specify a validator and developer-readable contract, for example:

```yaml
output:
  format: yaml
  validator: domain
  contract: canonical_domain
```

The generic structured-output syntax fixer runs before those validators. Scheduler YAML does not implement its own syntax-repair loop.

A scheduler is not complete until its `outputs:` block resolves exactly these four keys:

```yaml
outputs:
  prognosis: ...
  treatment: ...
  biomarker: ...
  germline: ...
```

`publish_domains` performs final canonical validation and writes the four scheduler-independent `FINAL_STATE.yaml` artifacts. Core evidence alignment and report synthesis start only after this boundary.

## What the scheduler owns

Scheduler YAML and scheduler prompt assets may control:

- task ordering;
- domain/variant/cell batching;
- evidence-normalisation passes;
- which earlier output is injected into a later prompt;
- adversarial/review terraces;
- deterministic assembly/patching using registered primitives;
- clinical synthesis of hard decisions plus surfaced `fact` and `reason`.

The scheduler does **not** own:

- case structuring or the invariant detected-variant sentence;
- blind ICC diagnosis;
- WHO5/CMC stabilisation;
- CMC derivation;
- card retrieval semantics;
- generic syntax repair and model retry machinery;
- canonical domain validators;
- fact/reason-to-card alignment;
- final report prose synthesis;
- sentence-to-fact matching or citation inheritance;
- final rendering/packaging.

## Developer commands

List schedulers:

```bash
python workflows/terraced_v3/step.py schedulers
```

Compile-check one scheduler without invoking a model:

```bash
python workflows/terraced_v3/step.py scheduler-check --scheduler evidence-first
```

The check validates scheduler YAML structure, step/dependency references, legal operations, prompt file existence, exact prompt-slot declarations and the four canonical outputs.

Inspect the execution plan:

```bash
python workflows/terraced_v3/step.py scheduler-plan --scheduler evidence-first
```

Then run normally:

```bash
python workflows/terraced_v3/step.py setup \
  --mode nel-validate-brief --case-id 1 \
  --scheduler evidence-first
```

## Adding a new scheduler

1. Copy `common/examples/minimal_scheduler.yaml` into a new `schedulers/<id>/scheduler.yaml` directory.
2. Set unique metadata (`id`, `order`, `description`).
3. Define ordered steps and explicit inputs.
4. Add only the local prompt templates the strategy genuinely needs.
5. Reuse shared prompt fragments for canonical contracts/invariants rather than copying them.
6. Make dependencies and earlier-output injections explicit in YAML.
7. End with the four canonical outputs.
8. Run `scheduler-check` and `scheduler-plan`.
9. Add deterministic tests for any new core primitive.
10. Run at least `nel-validate-brief 1` before treating the scheduler as production-usable.

## Design limit

The scheduler YAML is intentionally **not a general programming language**. It describes an auditable clinical information-flow graph over a constrained set of operations. If a strategy starts requiring arbitrary code inside YAML, the correct response is usually to add a reusable core primitive or reconsider the scheduler design.
