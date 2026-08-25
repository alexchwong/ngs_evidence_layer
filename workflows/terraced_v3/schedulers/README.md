# Terraced-v3 schedulers

Schedulers are declarative YAML instruction sets interpreted by the common scheduler engine. They define model-call flow, prompt assets, previous-output injection and registered deterministic operations. They do not contain Python.

For the full architectural map and contract lookup rules, read `../DEVEL.md` first.

## Folder layout

```text
schedulers/
├── diagnosis/
│   ├── default-diagnosis/
│   │   ├── scheduler.yaml
│   │   ├── prompts/
│   │   └── contracts/
│   └── minimal-diagnosis/
├── ptbg/
│   ├── common/contracts/
│   ├── domain/
│   ├── evidence-first/
│   ├── variant-centric/
│   ├── global-ledger/
│   └── adaptive-microtask/
└── summarization/
    ├── default-summarization/
    └── minimal-summarization/
```

A scheduler folder should contain only declarative assets: `scheduler.yaml`, `prompts/`, and `contracts/` as needed.

## Scheduler interface

Each scheduler declares its own input/output interface. These interfaces are not globally invariant.

```yaml
interface:
  inputs:
    case: {contract: core.case.structured}
  outputs:
    result: {contract: local.result}
```

`core.*` maps mechanically to `../contracts/core/...`. `local.*` maps to the current scheduler's `contracts/` directory. Relative paths may reference intentionally shared contracts.

A pipeline may connect two modules directly only if setup-time compatibility validation proves that the upstream output satisfies the downstream input contract. Otherwise use an explicit adapter module.

## Model step

```yaml
- id: adjudicate
  kind: model
  inputs:
    case: core.case.structured
    evidence: core.evidence.domain-current
  prompt:
    template: prompts/adjudicate.md
    inject:
      output_contract:
        contract_select:
          prognosis: ../common/contracts/prognosis-output.md
          treatment: ../common/contracts/treatment-output.md
      case: {input: case, render: json}
      evidence: {input: evidence, render: text}
  output:
    format: yaml
    validator: domain
    contract_select:
      prognosis: ../common/contracts/prognosis-output.md
      treatment: ../common/contracts/treatment-output.md
```

The model-facing structured output skeleton belongs in the contract Markdown, not the prompt template.

## Prompt injection

Static prompt fragment:

```yaml
shared_rules:
  prompt: ../../common/prompts/domain_task.md
```

Contract asset:

```yaml
output_contract:
  contract: local.output
```

Domain-selected contract:

```yaml
output_contract:
  contract_select:
    prognosis: ../common/contracts/prognosis-output.md
    treatment: ../common/contracts/treatment-output.md
```

Earlier model output:

```yaml
inputs:
  previous: steps.initial
prompt:
  inject:
    previous: {input: previous, render: yaml}
```

Every `{{slot}}` in a prompt must have exactly one injection declaration; undeclared or unused slots fail `scheduler-check` before runtime.

## Summarization provenance rule

Summarization schedulers consume immutable `core.statements.cited` rows. They must explicitly disposition every non-diagnostic statement as `include` or `omit`; diagnosis classification statements are mandatory. Sentence plans use `source_statement_ids`, and paraphrasing never chooses citations. Core publishes the ordered union of each source statement's locked `card_tags`.

Do not add an end-stage semantic evidence alignment or sentence-to-statement matching step: provenance must already be explicit in the scheduler artifacts.

## Deterministic operations

Scheduler YAML may call only registered operations from `scheduler_primitives.py`. Do not embed Python, expressions, lambdas, or arbitrary transforms in scheduler YAML. If a reusable deterministic operation is required, implement and test one named core primitive.

## Developer commands

```bash
python workflows/terraced_v3/step.py schedulers --phase ptbg
python workflows/terraced_v3/step.py scheduler-check --phase ptbg --scheduler evidence-first
python workflows/terraced_v3/step.py scheduler-plan --phase ptbg --scheduler evidence-first
```

After a scheduler is valid in isolation, connect it in a pipeline and run `pipeline-check`; that is where cross-module input/output compatibility is validated.
