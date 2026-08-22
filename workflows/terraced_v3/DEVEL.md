# Terraced-v3 developer guide

Terraced-v3 is intentionally asset-driven. A developer should be able to understand a pipeline or scheduler by following named assets rather than searching Python for hidden output templates.

## The four concepts

1. **Contract** — what a datum means and what its representation must contain.
2. **Scheduler** — how model calls and deterministic scheduler primitives transform inputs into outputs.
3. **Pipeline** — a validated directed acyclic graph (DAG) connecting core modules and schedulers.
4. **Python runtime** — execution mechanics and invariants that depend on the live case, retrieved cards, or other runtime state.

`README.md` is user-facing. This file is the architectural index for developers.

## Repository map

```text
terraced_v3/
├── DEVEL.md
├── README.md
├── contracts/
│   └── core/                    invariant/core-owned data contracts
├── modules/
│   └── core/                    core pipeline module interface assets
├── adapters/                    explicit deterministic pipeline adapters
├── schedulers/
│   ├── diagnosis/
│   ├── ptbg/
│   └── summarization/
├── pipelines/                   user-editable pipeline DAGs and model bindings
├── corpus_filters.yaml          authority-specific diagnosis corpus filtering + evidence-resolution limits
├── evidence_resolution.py       bounded diagnosis card extraction/pairing/audit
├── contract_registry.py         Markdown-contract loading and compatibility
├── module_registry.py           core/adaptor module asset loading
├── pipeline_registry.py         DAG parsing + setup-time compatibility checks
├── scheduler_engine.py          generic scheduler YAML interpreter
├── scheduler_primitives.py      registered deterministic scheduler operations
├── runtime.py                   case-dependent validators/invariants
├── model_client.py              provider calls
├── layout.py                    run-directory layout
└── step.py                      CLI and module execution
```

## Contract lookup rule

Every named core data reference maps mechanically to one Markdown file:

```text
core.a.b.c
    ↓
contracts/core/a/b/c.md
```

Examples:

```text
core.case.structured
→ contracts/core/case/structured.md

core.statements.cited
→ contracts/core/statements/cited.md

core.statements.reasonable-support-check
→ contracts/core/statements/reasonable-support-check.md
```

Scheduler-private contracts use `local.*` and resolve inside that scheduler:

```text
local.icc-output
→ <current scheduler>/contracts/icc-output.md
```

A literal relative contract path resolves from the asset declaring it. This is used for shared PTBG contracts, for example:

```text
../common/contracts/prognosis-output.md
```

The same lookup rule applies to scheduler-facing runtime `core.*` sources. For example:

```text
core.diagnosis.who5.active
→ contracts/core/diagnosis/who5/active.md

core.ptbg.task-scope
→ contracts/core/ptbg/task-scope.md

core.evidence.domain-current
→ contracts/core/evidence/domain-current.md
```

`scheduler-check` rejects a public `core.*` source that has no corresponding contract asset. This prevents undocumented magic runtime names from accumulating in scheduler YAML.

Pipeline edges use `<module-id>.<output-name>`. The output's contract is declared by that upstream module/scheduler and is shown by `pipeline-plan` and in the run's `pipeline-compiled.md`.

## Contract file format

Contracts are Markdown with deliberately small YAML frontmatter. The body is also suitable for model prompt injection.

```markdown
---
id: example.output
semantic_type: clinical.example
format: yaml
provides:
  - rows[].id
  - rows[].value
requires: []
validator: optional_validator_name
runtime_invariants:
  - optional_named_runtime_rule
---
# Example output

Return YAML only:

```yaml
rows:
  - id: X1
    value: "..."
```
```

The frontmatter is not intended to become a second programming language. It records only:

- `semantic_type`: what the datum means;
- `format`: YAML, JSON, Markdown, text, or service;
- `provides`: fields an output guarantees;
- `requires`: fields an input contract needs;
- optional validator/runtime-invariant names.

Complex case-dependent rules remain Python. The contract names those rules so they are discoverable.

## What stays in Python

Python should continue to own algorithms and live-state invariants, including:

- provider/model calls and token limits;
- generic YAML/JSON syntax repair;
- logging, retry handling, resume/checkpoint behavior;
- run-folder numbering and artifact persistence;
- WHO5 → CMC derivation and CMC history logic;
- exact case-specific variant/gene × diagnosis scope generation;
- verification that a card tag was actually supplied to a task;
- disease-scoped evidence permission;
- immutable reportable-statement reconciliation and tombstoning;
- binary statement/reason/card support checking with bounded local card repair;
- deterministic citation inheritance from summary `source_statement_ids`;
- reject-only semantic preservation checking after paraphrasing;
- registered deterministic scheduler operations and explicit adapters.

Do not move these into YAML expressions.

## Immutable reportable-statement provenance

Diagnosis resolves evidence in three bounded passes before committing a diagnosis snapshot. First, authority-filtered cards are rendered with deterministic line numbers and the model selects potentially relevant card-header lines. Second, the diagnosis question is answered using only that reduced bundle; each diagnosis is a canonical reportable `statement` with a `reason`, patient `case_refs`, and local `CARD nn` references. Python resolves those local references to immutable runtime `card_tags`. Third, each `statement + reason` is rendered immediately beside its selected interpretation(s) and receives a binary `supported` or `unsupported` assessment. Unsupported evidence gets bounded card-only repair; unresolved unsupported statements are recorded and blocked before summarization rather than regenerating the whole clinical artifact.

Diagnosis authority filtering is configured in `workflows/terraced_v3/corpus_filters.yaml`; the shipped defaults restrict WHO5 to Khoury 2022 and ICC to Arber 2022. Previously cited WHO5 cards are deterministically retained on reconsideration passes and prior runtime tags are localised back to `CARD nn` labels before the model sees them.

PTBG uses the same statement/evidence separation. Clinical reasoning produces only reportable statements, reasons and patient references; card fields are empty at that stage. At domain publication, core performs line-number relevance reduction, local-card pairing, deterministic runtime-ID resolution, binary support audit and bounded card-only repair.

Core reconciles accepted scheduler snapshots against a persistent statement ledger. Exact `statement + reason + case_refs + card_tags` retains the existing `statement_id`; a change to any of those immutable fields tombstones the old statement and creates a replacement ID. Subject/decision metadata may evolve without changing identity.

The active ledger handed to summarization contains `statement_id`, `domain`, `statement`, `reason`, `case_refs`, and `card_tags`. Summarization may omit non-diagnostic statements with an audit reason, but WHO5/ICC diagnosis statements are mandatory. Sentence plans use `source_statement_ids`; core computes sentence citations deterministically from those source statements.

## Prompt/output contracts

Model prompt templates should not restate structured output skeletons. Inject the contract asset instead:

```markdown
# Task
Do the clinical task.

{{output_contract}}

# Case
{{case}}
```

Scheduler YAML:

```yaml
prompt:
  template: prompts/task.md
  inject:
    output_contract:
      contract: local.output
    case:
      input: case
      render: json
```

For a domain-dependent contract:

```yaml
domain_contract:
  contract_select:
    prognosis: ../common/contracts/prognosis-output.md
    treatment: ../common/contracts/treatment-output.md
    biomarker: ../common/contracts/biomarker-output.md
    germline: ../common/contracts/germline-output.md
```

Earlier scheduler step output is injected with a normal declared input:

```yaml
inputs:
  previous: steps.initial

prompt:
  inject:
    previous: {input: previous, render: yaml}
```

## Scheduler interface

Each scheduler declares its own module interface:

```yaml
interface:
  inputs:
    case: {contract: core.case.structured}
  outputs:
    result: {contract: local.result}
```

Scheduler input/output names and exact shapes are **not globally invariant**. A different scheduler may expose a different interface. Compatibility is a pipeline concern.

Inside `steps`, scheduler YAML defines model-call topology and registered deterministic operations. Arbitrary Python or expression execution is not permitted.

## Pipeline DAG

A pipeline is an ordered DAG. Except for root `inputs.*`, every module input must be connected to an output of a module that appears earlier in the pipeline.

```yaml
modules:
  - id: diagnosis
    uses: scheduler.diagnosis.default-diagnosis
    inputs:
      case: structure.case
      panel_scope: inputs.panel_scope
      allowed_who5_diseases: inputs.allowed_who5_diseases
      card_identity: corpus.card_identity

  - id: ptbg
    uses: scheduler.ptbg.domain
    inputs:
      case: structure.case
      who5: diagnosis.who5
      routing: diagnosis.routing
      card_identity: corpus.card_identity
```

At setup, every edge is checked for:

1. upstream module/output existence;
2. semantic-type compatibility;
3. format compatibility;
4. downstream required fields being provided upstream;
5. topological ordering;
6. scheduler/prompt/contract validity;
7. provider/model-role configuration.

If contracts are intentionally incompatible, insert an explicit adapter module. Do not put transformation expressions into pipeline YAML.

## Core module assets

Core pipeline module inputs/outputs are not hidden in `step.py`; their inspectable interfaces live in:

```text
modules/core/*.yaml
```

The asset names the Python `handler`, but its input/output contracts remain file assets.

## Useful commands

```bash
python workflows/terraced_v3/step.py pipelines
python workflows/terraced_v3/step.py pipeline-check --pipeline self
python workflows/terraced_v3/step.py pipeline-plan --pipeline self

python workflows/terraced_v3/step.py schedulers --phase ptbg
python workflows/terraced_v3/step.py scheduler-check --phase ptbg --scheduler evidence-first
python workflows/terraced_v3/step.py scheduler-plan --phase ptbg --scheduler evidence-first

python workflows/terraced_v3/step.py contracts
python workflows/terraced_v3/step.py contract core.case.structured
```

Every setup also writes:

```text
intermediates/001_setup/pipeline-resolved.yaml
intermediates/001_setup/pipeline-compiled.md
```

`pipeline-resolved.yaml` freezes the selected DAG/model configuration for resume. `pipeline-compiled.md` lists every module edge and the exact upstream and expected contract files, with compatibility already checked.

## Adding a scheduler

1. Create `schedulers/<phase>/<name>/scheduler.yaml`.
2. Put model prompts in `prompts/`.
3. Put scheduler-specific structured contracts in `contracts/`.
4. Declare `interface.inputs` and `interface.outputs` using contracts.
5. Inject contract assets into prompts instead of restating YAML/JSON skeletons.
6. Use only registered scheduler primitives.
7. Run `scheduler-check`.
8. Connect it in a pipeline and run `pipeline-check`.
9. If an intended edge is incompatible, add an explicit deterministic adapter instead of inline transformation logic.

## Design boundary

The customization goal is broad, but evidence guarantees are not optional. Pipeline and scheduler assets may change model information flow and representations. Core Python still enforces non-negotiable safety properties such as WHO5-derived CMC routing, supplied-card provenance, and deterministic citation inheritance.
