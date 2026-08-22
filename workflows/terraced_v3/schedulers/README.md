# Terraced-v3 scheduler developer guide

Schedulers are interchangeable **task-partitioning strategies** for the same terraced-v3 clinical architecture. They do not own diagnosis/CMC routing, card retrieval semantics, validation/repair infrastructure, evidence alignment, prose synthesis, sentence-to-fact matching, citation rendering, or the invariant detected-variant sentence.

## Available schedulers

| Scheduler | ID | Partitioning strategy |
|---|---|---|
| Domain | `domain` | One compact call each for prognosis, treatment, MRD and germline. |
| Evidence first | `evidence-first` | Normalise relevant cards per domain, then adjudicate the patient from the normalised table. |
| Variant centric | `variant-centric` | One cross-domain call per detected variant; treatment is owned by the first variant for each gene; germline clinical picture is a separate case-level call. |
| Global ledger | `global-ledger` | One call fills all downstream domains, then an adversarial review returns a validated domain-replacement patch that Python applies. |
| Adaptive microtask | `adaptive-microtask` | Initial domain batches fill all cells, then only high-impact cells receive targeted keep/replace review terraces. |

## Selection

Selection is fixed at setup and stored in the numbered `intermediates/NNN_run_state/terraced-v3-run.json` for reproducibility:

```bash
python workflows/terraced_v3/step.py setup \
  --mode nel-validate-brief --case-id 1 \
  --scheduler variant-centric
```

List registered schedulers with:

```bash
python workflows/terraced_v3/step.py schedulers
```

The repository-level natural-language/skill invocation can pass the same selector, e.g. `nel-validate-brief 1 --terraced-v3 --scheduler global-ledger`.

`settings.json` / `settings.json.template` supplies only the default when setup omits `--scheduler`. Changing settings after a run has been created does **not** change that run's scheduler.

## Scheduler API

`workflows/terraced_v3/schedulers/__init__.py` is the registry. A scheduler module must export:

```python
SCHEDULER_ID = "my-scheduler"
DESCRIPTION = "Short developer-facing description."

def run(ctx):
    ...
```

Register the module in `SCHEDULER_MODULES`.

The `SchedulerContext` in `schedulers/common.py` exposes the intentionally narrow shared surface:

- immutable structured case;
- settled WHO5 diagnoses and final deterministic CMC set;
- canonical downstream task scopes/contracts;
- lazily retrieved disease-scoped evidence for a domain;
- the shared validated-model-call function;
- file helpers and status logging.

A scheduler must ultimately write these four canonical artifacts through the shared layout helpers. They appear in numbered intermediate directories, for example:

```text
intermediates/NNN_prognosis_state/FINAL_STATE.yaml
intermediates/NNN_treatment_state/FINAL_STATE.yaml
intermediates/NNN_biomarker_state/FINAL_STATE.yaml
intermediates/NNN_germline_state/FINAL_STATE.yaml
```

The `NNN` values are creation-order dependent and must never be hard-coded. Scheduler-specific scratch/state belongs under `layout.scheduler_dir(...)`; a scheduler must not create root-level domain or `scheduler/` directories.

Before the clinical stage completes, `step.py` validates all four against the same canonical proformas regardless of scheduler. This is the compatibility boundary that allows scheduler experiments without changing the pipeline tail.

## Canonical decision scopes

The shared contracts in `schedulers/common.py` define:

- prognosis: every `variant × final WHO5 diagnosis`;
- treatment: every unique `gene × final WHO5 diagnosis`;
- MRD/biomarker: every `variant × final WHO5 diagnosis`;
- germline: every detected variant plus one case-level clinical-picture decision.

Concurrent neoplasms are therefore preserved in every scheduler. Evidence alignment later prevents a card retrieved only for one diagnosis from citing a fact scoped only to another diagnosis.

## What schedulers must not change

Schedulers must not:

- author or edit CMCs;
- use ICC for routing or downstream clinical reasoning;
- change stable variant IDs, gene symbols or final WHO5 diagnoses;
- bypass `validated_model_task`;
- write final prose or citations;
- alter the invariant `detected_variants_summary`;
- read validation marking criteria.

Clinical candidate card tags remain non-authoritative. The shared evidence-alignment stage independently decides final citations from `fact + reason` semantics.

## Adding a scheduler

1. Add a module under `workflows/terraced_v3/schedulers/`.
2. Reuse `common.task_specs()` and `common.contract()` unless the scheduler only changes batching/terracing.
3. Route every model artifact through `ctx.call_yaml(...)` with an appropriate deterministic validator.
4. Convert scheduler-specific intermediate outputs into the four canonical `FINAL_STATE.yaml` files.
5. Register the scheduler in `schedulers/__init__.py`.
6. Add structural/unit tests and run at least `nel-validate-brief 1` before considering it usable.

Do not add scheduler-specific logic to evidence alignment, synthesis or final rendering unless the canonical ledger schema itself has deliberately changed.

## Current adaptive escalation rule

The prototype `adaptive-microtask` scheduler reviews only high-impact cells after its initial batches:

- prognosis: `favorable` or `adverse`;
- treatment: any positive drug-target or resistance decision;
- MRD: `mrd_usable: true`;
- germline: `potentially_germline: true` or a clinical-picture state other than `false`.

This is deliberately simple. Future escalation can add evidence conflict, missing candidate support, model uncertainty or deterministic cross-cell consistency checks without changing the scheduler API.

## Structured-output syntax repair

All scheduler YAML calls flow through `scripts/core/syntax_repair/` before task validation. Schedulers must not implement separate syntax-repair loops.
