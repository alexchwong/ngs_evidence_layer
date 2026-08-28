# Customising `proforma_v1` workflows

`workflow/default.yaml` is the shipped workflow. Copy it to experiment; do not edit Python merely to change clinical ordering, prompts, compatible proformas, conditions, evidence routing, or native-self batching.

```bash
cp workflows/proforma_v1/workflow/default.yaml \
   workflows/proforma_v1/workflow/my_experiment.yaml

python workflows/proforma_v1/step.py workflow-check \
  --workflow workflow/my_experiment.yaml
```

Run either adapter with the same selected file:

```bash
python workflows/proforma_v1/step.py setup ... --workflow workflow/my_experiment.yaml
python workflows/proforma_v1/self.py setup ... --workflow workflow/my_experiment.yaml
```

The workflow path and SHA-256 are frozen into run state. Resume refuses a workflow that has changed underneath an incomplete run.

## What the YAML owns

The selected workflow owns logical operations, true dependencies (`needs`), conditions, prompts, output schemas, allow-listed checks/transforms/assemblers, evidence policy/barriers, review feedback routing, native-self batch membership, and declared executor-specific omissions.

`needs` means a real data/control dependency. It must not be used merely to request provider call order. Provider execution can physically process independent ready operations one at a time; native self may coalesce simultaneously-ready operations that share a `self_group`.

Example:

```yaml
self_groups:
  ptbg:
    strategy: batch_ready

steps:
  prognosis:
    type: model
    needs: [diagnosis.finalize]
    execution:
      self_group: ptbg

  treatment:
    type: model
    needs: [diagnosis.finalize]
    execution:
      self_group: ptbg
```

The compiler rejects a self group containing operations that depend on one another.

## Executor-specific omissions

An intentional adapter difference must be visible in YAML:

```yaml
report.preservation:
  type: model
  needs: [report.write]
  execution:
    self:
      enabled: false
```

The logical trace records this as `skipped: executor_disabled`. Do not hide equivalent decisions inside `self.py` or `step.py`.

## Prompts and runtime inputs

Prompt assets may use static includes plus declared runtime placeholders:

```markdown
{{ include "includes/shared.md" }}

Previous audit:
{{ input.previous_audit }}
```

The input must be declared in the step:

```yaml
inputs:
  previous_audit:
    from: feedback.prognosis_audit
    optional: true
```

Supported bindings are deliberately bounded (`run.*`, `assets.*`, `artifacts.*`, `settings.*`, `feedback.*`, and `owner.cards`). No expression evaluation or function calls are allowed.

## Compatible proforma/schema experiments

A step may point at another prompt, JSON Schema, and—where used—a stage/proforma asset beneath the workflow `asset_root`:

```yaml
prognosis:
  stage: stages_experimental/prognosis.yaml
  prompt: prompts/experimental/prognosis.md
  output:
    artifact: prognosis
    format: yaml
    schema: schemas/experimental/prognosis.json
```

Custom stage assets use the same allow-listed stage meta-schema/rule/transform registries as shipped stages. They must retain the canonical downstream semantics required by the selected registered transforms. New executable deterministic behaviour still requires a reviewed Python registry extension; YAML cannot import code.

For an external experiment package, set `asset_root` to a trusted directory and keep all referenced prompts/schemas/stage assets beneath it. Path escape is rejected.

## Evidence match passes

The evidence-assignment step may choose how many matcher passes are available:

```yaml
steps:
  evidence.assignment:
    evidence:
      policy: literature_support
      timing: deferred
      cards: {from: owner.cards}
      match_passes: 2
```

Pass 1 receives every reportable fact with candidate evidence. Each later pass is conditional and receives only facts that still have zero matched cards. `match_passes: 1` disables the rescue pass; values from 1 to 10 are accepted. Match and audit model inputs are rendered as isolated `<fact-N>...</fact-N>` JSON blocks, so cards from one fact are not visible inside another fact's reasoning envelope. Audit receives only cards positively selected by the matcher.

## Semantic audit feedback

Schema/deterministic validation failure automatically retries the same model operation; this does not require a workflow edge.

For a *valid* audit artifact that semantically passes/fails another operation, use bounded `review` routing:

```yaml
prognosis:
  type: model
  needs: [diagnosis.finalize]
  inputs:
    previous_audit:
      from: feedback.prognosis_audit
      optional: true
  prompt: prompts/prognosis.md
  output:
    artifact: prognosis
    format: yaml
    schema: schemas/prognosis.json

prognosis.audit:
  type: model
  needs: [prognosis]
  prompt: prompts/prognosis_audit.md
  output:
    artifact: prognosis_audit
    format: yaml
    schema: schemas/prognosis_audit.json
  review:
    target: prognosis
    verdict:
      path: accepted
      pass_values: [true]
    on_pass:
      continue: true
    on_fail:
      retry_target: true
      feedback:
        from: artifacts.prognosis_audit
        as: previous_audit
      max_cycles: 2
      exhausted:
        action: stop
```

On failure, the engine persists the feedback, invalidates the reviewed target and its dependent path, and reruns it. Native-self cycle/feedback state survives process boundaries. `max_cycles` is mandatory; arbitrary YAML cycles are not supported.

A review may instead route to another declared step:

```yaml
on_fail:
  route_to: evidence.adjudication
```

Allowed exhausted actions are intentionally small: `stop`, `suppress`, `continue_with_dissent`, and `route_to`.

## Validation and tests

Compile before running a custom workflow:

```bash
python workflows/proforma_v1/step.py workflow-check --workflow workflow/my_experiment.yaml
```

Workflow-specific tests use `unittest`:

```bash
python -m unittest discover -s workflows/proforma_v1/tests -p "test_*.py"
```

A useful experiment should be possible by copying a YAML and its assets; if changing the experiment requires editing executor orchestration, the abstraction boundary is probably wrong.
