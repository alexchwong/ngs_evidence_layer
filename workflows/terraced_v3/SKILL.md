---
name: terraced-v3
description: Rapid typed-hard-fact terraced workflow for ngs-report and NEL validation modes.
---

# Terraced v3

`workflow.yaml` is the canonical pipeline definition. `step.py` executes it. Clinical reasoning is frozen into typed hard facts before prose generation.

## Supported modes

- `ngs-report --case-file case.md`
- `nel-demo --example N`
- `nel-validate --case-id ID`
- `nel-validate-function --case-id ID`
- `nel-validate-brief --case-id ID`

## Setup

```bash
python workflows/terraced_v3/step.py setup --mode nel-validate-brief --case-id 1 --model-profile self --scheduler domain
```

The command prints the timestamped work directory. Then run:

```bash
python workflows/terraced_v3/step.py run --work-dir <work-dir>
```

For a delegated provider, select a configured profile during setup or with `provider <profile>`.


## Scheduler selection

Terraced-v3 supports five interchangeable schedulers:

- `domain` — one compact task per downstream domain;
- `evidence-first` — normalise evidence, then adjudicate;
- `variant-centric` — one cross-domain task per detected variant;
- `global-ledger` — one global hard-fact pass plus adversarial patch review;
- `adaptive-microtask` — initial batches plus targeted review of high-impact cells.

Select one at setup with `--scheduler <id>`. The selection is persisted in the run state and cannot drift if `settings.json` later changes. Schedulers are declarative `schedulers/<id>/scheduler.yaml` instruction sets interpreted by one core scheduler engine; scheduler-specific model instructions live beside them under `prompts/`. `python workflows/terraced_v3/step.py schedulers` lists discovered schedulers. Use `scheduler-check --scheduler <id>` to validate YAML/prompt wiring without a model and `scheduler-plan --scheduler <id>` to inspect execution order. Developer details are in `schedulers/README.md`.

Examples:

```bash
python workflows/terraced_v3/step.py setup --mode nel-validate-brief --case-id 1 --scheduler evidence-first
python workflows/terraced_v3/step.py setup --mode nel-validate-brief --case-id 1 --scheduler variant-centric
python workflows/terraced_v3/step.py setup --mode nel-validate-brief --case-id 1 --scheduler global-ledger
python workflows/terraced_v3/step.py setup --mode nel-validate-brief --case-id 1 --scheduler adaptive-microtask
```

## Self-provider handoff contract

A self-bound model operation exits with code 10 and prints `PROMPT=` and `OUTPUT=`. Read the packaged prompt, write only the requested complete artifact to `OUTPUT`, then rerun the same `run` command. Deterministic validation will either accept it, safely repair representation-only defects, or package actionable validator feedback for correction.

Do not read validation marking criteria during a validation run. `runtime.setup_assets` retrieves only the selected case stem. Marking is package-only.

## Clinical architecture

1. Structure case with stable variant/case-fact IDs and non-authoritative `bootstrap_cmcs`.
2. Initialise whole-corpus deterministic card identities.
3. Run an ICC pass blind to WHO5; freeze the result.
4. Run repeated WHO5 passes. Python derives CMCs only from WHO5 `schema_disease`. If CMC changes, diagnosis retrieval retains cards from every old and new CMC until WHO5 survives a targeted reconsideration plus adversarial review. Final downstream routing uses current CMCs only.
5. The selected scheduler fills the same canonical prognosis, treatment, MRD and germline hard-fact proformas. Concurrent diagnoses are independently scoped.
6. Independently align surfaced fact/reason pairs to evidence cards.
7. Freeze the cited ledger.
8. Synthesize prose from locked facts only.
9. Semantically align report sentences back to locked facts; citations inherit deterministically.
10. Deterministically prepend the invariant source-faithful detected-variant sentence, render Vancouver references and package output.

ICC is never an input to WHO5, CMC derivation, downstream retrieval or downstream clinical decisions.

## Validation/repair

`scripts/core/syntax_repair/` is the generic YAML/JSON syntax fixer. For structured model output, use it before task validation: conservative deterministic serialization cleanup first, then at most two compact syntax-only model repairs. The syntax-only prompt contains the parser error and broken artifact but not the original clinical context, and explicitly forbids any change to factual/informational content. Reject model-assisted repairs unless recoverable lexical content and protected numeric/ID/card-tag tokens are preserved exactly. If both syntax repairs fail, allow one short same-answer reserialization request before returning to the ordinary clinical retry path. Syntax repair is separate from the clinical retry count and must be logged under that numbered model operation's `syntax-repair/` folder.

`scripts/core/validated_model_task.py` remains workflow-neutral and owns structured validation issues plus complete schema/invariant retry instructions. Task validators in `runtime.py` own proforma-specific invariants. Neither deterministic syntax repair nor the syntax-repair model may make a clinical judgement.

## Run-directory contract

The run root contains the immutable true input `case.md`, the two generated namespaces `model_steps/` and `intermediates/`, and genuine/operational outputs such as `report-final.md`, validation/debug packages, `workflow.json`, and `workflow.log`. Do not recreate root-level `diagnosis/`, domain, scheduler, evidence, synthesis, input, or state directories.

Subdirectories directly under `model_steps/` and `intermediates/` are named `NNN_<meaning>` using three-digit order of actual creation within that namespace. Reuse an existing numbered directory on resume; do not renumber completed operations. Model syntax-repair files stay nested inside the owning model step.

Important intermediate artifacts include WHO5/ICC states, routing history, domain `FINAL_STATE.yaml` files, the cited fact ledger, report draft, and sentence-to-fact alignment. Their exact `NNN_` prefixes are run-dependent; discover them by semantic suffix rather than assuming a fixed number.

## Main outputs

- `case.md` — immutable true case input copy at root
- `report-final.md` — clinician-facing report
- `terraced-v3-debug.zip` — complete debug package
- validation marking package ZIP — validation modes only
- `workflow.log` — complete CLI log

All model operations and failed attempts are under numbered `model_steps/NNN_*` directories.
