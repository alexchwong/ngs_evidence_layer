---
name: terraced-v3
description: Contract-driven DAG workflow with declarative schedulers and setup-time interface validation.
---

# Terraced v3

Terraced-v3 is configured by a **pipeline DAG**. A pipeline connects core modules, diagnosis/PTBG/summarization schedulers, and optional explicit adapters. Every module input/output is described by an inspectable Markdown contract asset. Setup validates every pipeline edge before any model call is made.

`README.md` is the user quickstart. `DEVEL.md` is the developer architecture/index and explains where every contract, scheduler, pipeline, prompt, module and Python invariant lives.

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

A successful setup snapshots both `pipeline-resolved.yaml` and `pipeline-compiled.md` in setup intermediates. The compiled document lists each module edge, upstream contract, expected downstream contract, and compatibility result.

## Contracts are the data specification

Every named core reference resolves mechanically:

```text
core.a.b.c
→ workflows/terraced_v3/contracts/core/a/b/c.md
```

Scheduler-private `local.*` references resolve under that scheduler's `contracts/` directory. Contract files are Markdown with compact YAML frontmatter plus a readable/model-facing YAML/JSON/output example. Structured output skeletons should live in contract files, not be duplicated in Python or prompt templates.

Inspect contracts with:

```bash
python workflows/terraced_v3/step.py contracts
python workflows/terraced_v3/step.py contract core.case.structured
```

## Pipeline DAG

Pipeline YAML under `pipelines/` declares:

- provider configuration;
- external/root inputs and their contracts;
- an ordered DAG of `core.*`, `scheduler.<phase>.*`, and optional `adapter.*` modules;
- explicit input edges such as `who5: diagnosis.who5`;
- model/temperature/token-cap bindings for every model role.

Scheduler inputs/outputs are **not globally fixed**. Each scheduler declares its own interface contracts. During setup, every connected edge is checked for upstream output existence, semantic-type compatibility, format compatibility, and required fields. Intentional representation mismatches must use an explicit adapter rather than YAML transformation expressions.

Developer-only scheduler overrides remain available when the replacement scheduler is interface-compatible with the existing pipeline edges:

```bash
python workflows/terraced_v3/step.py setup \
  --mode nel-validate-brief --case-id 1 --pipeline self \
  --ptbg-scheduler evidence-first
```

## Scheduler assets

Schedulers are declarative YAML plus local prompt/contract assets under:

```text
schedulers/
├── diagnosis/
├── ptbg/
└── summarization/
```

Do not create scheduler-specific Python runners. Scheduler YAML declares model-call topology, inputs, prompt/template injection, output contracts, and registered deterministic operations. Python implements the generic engine and runtime-dependent invariants.

```bash
python workflows/terraced_v3/step.py schedulers --phase ptbg
python workflows/terraced_v3/step.py scheduler-check --phase ptbg --scheduler evidence-first
python workflows/terraced_v3/step.py scheduler-plan --phase ptbg --scheduler evidence-first
```

See `schedulers/README.md` for authoring details and `DEVEL.md` for namespace/asset lookup rules.

## Core invariants

Python/core continues to own algorithms and live-state guarantees, including:

- deterministic WHO5 → CMC derivation and diagnosis CMC-history logic;
- exact case-specific variant/gene × diagnosis scope where required by a named runtime invariant;
- verification that model card tags were actually supplied to the task;
- disease-scoped evidence permission;
- generic YAML/JSON syntax repair and retry handling;
- evidence/statement provenance, citation trust and deterministic citation inheritance;
- invariant detected-NGS-variant sentence;
- logging, resume/checkpointing, run-directory layout and packaging.

A contract asset documents named runtime invariants; it does not reimplement them in YAML.

## Default clinical flow

The shipped default pipelines currently connect:

```text
case → structure → corpus → default-diagnosis → domain PTBG
     → core immutable statement-ledger collection → default-summarization → core finalise
```

`default-diagnosis` preserves blind ICC, iterative WHO5/CMC reconsideration, cumulative old+new CMC diagnosis evidence, adversarial confirmation and oscillation protection. ICC never determines CMC.

The five PTBG schedulers are `domain`, `evidence-first`, `variant-centric`, `global-ledger`, and `adaptive-microtask`.

Each surfaced diagnosis/PTBG statement carries a reason and patient `case_refs`. Evidence resolution separately pairs literature cards, resolves immutable card IDs deterministically, and performs a binary support audit before the statement can reach summarization.

`default-summarization` explicitly decides statement include/omit, sentence order, merge and split; diagnosis statements are mandatory. A reject-only semantic-preservation check guards paraphrasing. Core derives sentence citations deterministically from `source_statement_ids` and creates `sentence-card-interpretations.yaml`; there is no end-stage semantic evidence alignment.

## Self-provider handoff

A self-bound model operation exits with code 10 and prints `PROMPT=` and `OUTPUT=`. Read the packaged prompt, write only the requested complete artifact to `OUTPUT`, then rerun the same `run` command. Do not bypass the packaged validator/retry path.

Do not read validation marking criteria during a validation run. Marking is package-only.

## Structured-output repair

`scripts/core/syntax_repair/` repairs YAML/JSON syntax before task validation. It performs conservative representation-only cleanup, then at most two syntax-only model repairs with strict content preservation. Syntax repair receives no clinical context and must not change clinical content. Bare exact 12-character hashes in known card-tag fields may be canonicalized to `[card:<hash>]`; the normal validator still requires that card to have been supplied to the task.

## Run-directory contract

The run root contains immutable `case.md`, numbered `model_steps/`, numbered `intermediates/`, and genuine outputs such as `report-final.md`, debug/validation packages, `workflow.json`, and `workflow.log`.
