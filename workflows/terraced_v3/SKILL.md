---
name: terraced-v3
description: Pipeline-composed, declarative terraced workflow with invariant diagnosis, PTBG and summarization interfaces.
---

# Terraced v3

`workflow.yaml` defines the core phase spine. `step.py` executes it. A **pipeline** is the normal user-facing configuration: it selects one diagnosis scheduler, one PTBG scheduler, one summarization scheduler, and provider/model/token-cap bindings for every model role.

## Supported modes

- `ngs-report --case-file case.md`
- `nel-demo --example N`
- `nel-validate --case-id ID`
- `nel-validate-function --case-id ID`
- `nel-validate-brief --case-id ID`

## Normal setup and run

```bash
python workflows/terraced_v3/step.py setup \
  --mode nel-validate-brief --case-id 1 --pipeline self
```

Then:

```bash
python workflows/terraced_v3/step.py run --work-dir <work-dir>
```

Shipped pipelines are `self`, `lmstudio`, and `openrouter`.

```bash
python workflows/terraced_v3/step.py pipelines
python workflows/terraced_v3/step.py pipeline-check --pipeline self
python workflows/terraced_v3/step.py pipeline-plan --pipeline self
```

Pipeline YAML is under `pipelines/`. It specifies provider, scheduler selection, and `model`/`temperature`/`max_tokens` for all mandatory roles: `structure`, `diagnosis`, `ptbg`, `evidence_alignment`, `summarization`, `summarization_review`, and `syntax_repair`.

The resolved pipeline is snapshotted during setup so a resumed run cannot silently drift if repository configuration later changes.

## Scheduler phases

There are three independently selectable scheduler phases with fixed core-defined interfaces:

1. **diagnosis** → `icc`, `who5`, `routing`;
2. **ptbg** → canonical `prognosis`, `treatment`, `biomarker`, `germline` states;
3. **summarization** → canonical ordered report sentences paired to accepted fact IDs/card tags.

Schedulers are declarative YAML plus prompt assets, interpreted by one generic engine. Do not create scheduler-specific Python runners.

List/check/inspect them with:

```bash
python workflows/terraced_v3/step.py schedulers
python workflows/terraced_v3/step.py schedulers --phase ptbg
python workflows/terraced_v3/step.py scheduler-check --phase diagnosis --scheduler default-diagnosis
python workflows/terraced_v3/step.py scheduler-plan --phase summarization --scheduler default-summarization
```

Developer-only phase overrides can be supplied at setup:

```bash
python workflows/terraced_v3/step.py setup \
  --mode nel-validate-brief --case-id 1 --pipeline self \
  --diagnosis-scheduler minimal-diagnosis \
  --ptbg-scheduler evidence-first \
  --summarization-scheduler minimal-summarization
```

See `schedulers/README.md` for scheduler YAML, prompt templates, prompt-fragment injection, prior-output injection, operations and contracts. See `pipelines/README.md` for pipeline composition/model configuration.

## Core invariants

Core, not schedulers, owns:

- case structure and stable IDs;
- deterministic WHO5 → CMC derivation;
- diagnosis retrieval semantics, including cumulative old+new CMC evidence during stabilisation;
- canonical phase validators;
- YAML/JSON syntax repair;
- evidence/card trust and semantic fact/reason↔card alignment;
- sentence provenance validation and deterministic citation inheritance;
- invariant detected-variant sentence;
- filesystem/logging/resume behaviour and packaging.

ICC never influences WHO5 routing or CMC.

`default-diagnosis` is the recommended diagnosis scheduler and preserves blind ICC, repeated WHO5/CMC reconsideration, adversarial confirmation and oscillation protection. `minimal-diagnosis` is only a working interface example.

The five PTBG schedulers are `domain`, `evidence-first`, `variant-centric`, `global-ledger`, and `adaptive-microtask`.

`default-summarization` performs draft → sentence/fact semantic alignment with a bounded coverage rewrite. `minimal-summarization` is a one-call interface example.

## Citation/provenance output

PTBG produces clinical decisions plus surfaced `fact` and `reason`; independent core alignment verifies supporting cards and freezes citations in the fact ledger. Summarization may only map sentences to those facts. Core then deterministically writes `sentence-card-interpretations.yaml`, pairing every final report sentence to the interpretations of the card tags inherited from its matched facts.

## Self-provider handoff

A self-bound model operation exits with code 10 and prints `PROMPT=` and `OUTPUT=`. Read the packaged prompt, write only the requested complete artifact to `OUTPUT`, then rerun the same `run` command. Do not bypass the packaged validator/retry path.

Do not read validation marking criteria during a validation run. Marking is package-only.

## Structured-output repair

`scripts/core/syntax_repair/` repairs YAML/JSON syntax before task validation. It performs conservative representation-only cleanup, then at most two syntax-only model repairs with strict content preservation. Syntax repair receives no clinical context and must not change facts. Bare 12-character hashes in known card-tag fields are safely canonicalized only when they exactly match a supplied card.

## Run-directory contract

The root contains immutable `case.md`, numbered `model_steps/`, numbered `intermediates/`, and genuine outputs (`report-final.md`, debug/validation packages, `workflow.json`, `workflow.log`). Do not recreate old root-level diagnosis/domain/evidence/synthesis/state directories.

Important intermediates include the resolved pipeline, diagnosis routing state, PTBG `FINAL_STATE.yaml` files, cited fact ledger, canonical summary state and `sentence-card-interpretations.yaml`.
