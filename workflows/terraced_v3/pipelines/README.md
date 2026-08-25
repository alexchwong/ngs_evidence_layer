# Terraced-v3 pipelines

A pipeline is the normal user-facing configuration. It is an ordered DAG connecting root inputs, core modules and schedulers, plus provider/model-role bindings.

Shipped defaults:

- `self.yaml`
- `lmstudio.yaml`
- `openrouter.yaml`

## Module graph

```yaml
pipeline:
  id: self
  version: 2

inputs:
  case: {contract: core.input.case-md}
  panel_scope: {contract: core.setup.panel-scope}

modules:
  - id: structure
    uses: core.structure-case
    inputs:
      case: inputs.case
      panel_scope: inputs.panel_scope
      allowed_bootstrap_cmcs: inputs.allowed_bootstrap_cmcs

  - id: diagnosis
    uses: scheduler.diagnosis.default-diagnosis
    inputs:
      case: structure.case
      panel_scope: inputs.panel_scope
      allowed_who5_diseases: inputs.allowed_who5_diseases
      card_identity: corpus.card_identity
```

Except for `inputs.*`, every module input must reference an output of an earlier module. The listed order is therefore a topological order of the DAG.

## Setup-time validation

`pipeline-check` loads every module/scheduler contract and verifies:

- all source modules and named outputs exist;
- source modules occur upstream;
- semantic types are compatible;
- formats are compatible;
- every field required downstream is declared by the upstream contract;
- scheduler YAML/prompt assets compile;
- all provider/model roles have valid model and token-cap settings.

An intentional mismatch requires an explicit deterministic adapter. Pipeline YAML does not support arbitrary transformation expressions.

```bash
python workflows/terraced_v3/step.py pipeline-check --pipeline self
python workflows/terraced_v3/step.py pipeline-plan --pipeline self
```

On setup, the validated configuration is frozen into `pipeline-resolved.yaml`, and `pipeline-compiled.md` records each edge plus both exact contract files.

## Provider/model roles

Each pipeline defines these independent roles:

```text
structure
diagnosis
ptbg
statement_evidence_check
summarization
paraphrasing
semantic_preservation_check
syntax_repair
```

Each role has its own model, temperature and `max_tokens`.

See `../DEVEL.md` for contract assets, scheduler interfaces and adapter development.
