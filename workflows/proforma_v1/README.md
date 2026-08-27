# proforma_v1 — Phase 2 declarative workflow engine

`proforma_v1` is the populated `terraced_v6` clone used to migrate the logical clinical workflow into one validated declarative graph without intentionally changing clinical behaviour. `terraced_v6` remains the frozen reference.

## Canonical workflow

`workflow.yaml` is now the sole source of logical operation order and dependencies. It currently compiles to 17 logical operations spanning structure, corpus, WHO/ICC diagnosis, PTBG, evidence review, deterministic blocks and report writing. Provider and native-self execution both consume the same compiled graph; executor metadata may coalesce physical model work but cannot define another clinical sequence.

Validate it before running:

```bash
python workflows/proforma_v1/step.py workflow-check
python workflows/proforma_v1/step.py pipeline-check --pipeline lmstudio
```

The compiler rejects malformed/duplicate YAML, workflow-schema violations, missing or escaping prompt/schema assets, prompt include cycles, undeclared placeholders, unknown roles/checks/assemblers/transforms/evidence policies, unresolved artifact references, dependency cycles, artifact collisions, unsupported conditions, and unsafe deferred-evidence barriers.

## Prompts and placeholders

Existing static prompt includes continue to use:

```text
{{ include "includes/common.md" }}
```

Runtime placeholders are deliberately bounded to declared inputs and the output template:

```text
{{ input.case }}
{{ output.template }}
```

No expressions, function calls, arbitrary Python, imports or shell execution are supported.

## Structured output validation

New declarative components can use the generic pipeline in `engine/schema_validation.py`:

```text
raw output
  -> parse YAML/JSON/text
  -> JSON Schema
  -> deterministic checks
  -> optional deterministic assembly
  -> optional final schema
  -> committed artifact
```

The existing `stage_validation.py` remains the compatibility adapter for current stage contracts so Phase 1 replay feedback remains unchanged.

### Generic checks

`engine/checks.py` allow-lists common runtime checks including `equals`, `equals_source`, `subset`, `member_of`, `unique`, `sequential_ids`, `one_row_per`, `required_when`, `null_when`, `field_matches_source`, and `ordered_by_source`.

Current v6 stage-rule names are also allow-listed and continue to execute through the existing `rules.py` compatibility path. Developer-owned specialised checks use the `custom` rule plus an allow-listed handler registered in Python; YAML cannot supply an import path or executable expression.

### Deterministic assemblers

`engine/assemblers.py` intentionally stays small: `passthrough`, `object_merge`, `keyed_rows`, and `list_rows`. `keyed_rows` is the preferred pattern for future model-owned partial forms: Python owns canonical IDs/order/identity fields and merges only allow-listed model-owned answer fields.

### Registered transforms

Complex deterministic logic remains an allow-listed Python extension point in `engine/transforms.py`. YAML selects a registered name; it cannot provide arbitrary code. Current specialised v6 transforms remain delegated to established deterministic handlers where moving their data shape would alter Phase 2 behaviour.

## Conditions

The runner supports a deliberately small vocabulary: setting equality, artifact-changed state, non-empty artifact state, boolean artifact state, and registered predicates. General expressions are not supported. Complex clinical conditions should be calculated deterministically into an artifact and gated on that artifact.

## Generic evidence triplet

`engine/evidence.py` owns model-independent evidence mechanics:

1. deterministic declarative claim extraction and owner evidence envelopes;
2. asymmetric audit targeting;
3. deterministic resolver/auditor disagreement detection;
4. cropped adjudication validation.

If assignment selects cards, audit only those cards. If assignment selects zero cards, audit the full eligible candidate pool so a false-negative zero assignment can be rescued. Adjudication is permitted only for disputed claim/card pairs.

Evidence policies are declared centrally in `workflow.yaml`. The engine supports `blocking` and `deferred` timing. The compiler requires every deferred review to have a downstream adjudication barrier and rejects non-evidence consumers that can bypass it.

Phase 2 deliberately retains the current v6 batched evidence behaviour. Owner-local evidence review and routing-critical WHO1 blocking evidence are Phase 3 changes.

## Provider execution

```bash
python workflows/proforma_v1/step.py setup --mode nel-validate-brief --case-id 1 --pipeline lmstudio
python workflows/proforma_v1/step.py run --work-dir <printed-work-dir>
```

`step.py` supplies operation handlers to the shared runner rather than declaring clinical order itself.

## Native self execution

Native self setup and bounded handoffs remain available through `self.py`. `self.py` uses the same compiled workflow graph as provider execution and maps each logical step to deterministic work or a bounded self handoff.

## Regression and replay

Run all workflow tests with `unittest`:

```bash
python -m unittest discover -s workflows/proforma_v1/tests -p "test_*.py"
```

Phase 1 replay fixtures remain the behavioural oracle. Architectural migration in Phase 2 must keep those fixtures green.

## Adding a proforma safely

1. Add/retain the prompt asset and structured output schema.
2. Add the stage contract if the model artifact uses the compatibility stage layer.
3. Add one logical operation to `workflow.yaml` with explicit dependencies and output artifact.
4. Use generic checks/assemblers where practical; register specialised deterministic Python only when necessary.
5. Declare evidence policy/timing if the output creates literature-dependent claims.
6. Run `workflow-check`.
7. Run the `unittest` replay/regression suite.

## Phase 2 limits / next phase

There are no intentional clinical changes in Phase 2. Some v6-compatible physical work is still coalesced inside operation handlers to preserve behaviour. Phase 3 should add `reconsider_after_cmc_expansion`, WHO1 blocking `diagnosis_complete_support`, owner-local downstream assignment/audit, and deferred batched adjudication only where dependency-safe.
