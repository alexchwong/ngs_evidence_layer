# Terraced v3

Terraced v3 is a rapid prototype that separates **clinical decisions** from **report prose**. It keeps the reliable execution assets of v2 but replaces the large evolving prompt state with small typed hard-fact proformas.

## Quickstart

```bash
python workflows/terraced_v3/step.py setup --mode ngs-report --case-file case.md
python workflows/terraced_v3/step.py run --work-dir <printed-work-dir>
```

Validation example:

```bash
python workflows/terraced_v3/step.py setup --mode nel-validate-brief --case-id 1 --model-profile self
python workflows/terraced_v3/step.py run --work-dir <printed-work-dir>
```

Configure a delegated provider with:

```bash
python workflows/terraced_v3/step.py provider openrouter
```

## Architecture

```text
case.md
  │
  ▼
structured case + stable IDs
  │
  ├────────────► independent ICC ────────────────┐
  │                                              │ frozen
  ▼                                              │
WHO5 pass 1                                      │
  │                                              │
  ▼                                              │
Python WHO5 → CMC set                            │
  │                                              │
  ▼                                              │
cumulative old + new CMC diagnosis cards        │
  │                                              │
  ▼                                              │
targeted reconsideration → adversarial review   │
  │                                              │
  ▼ stable WHO5                                  │
final current CMC set only                       │
  │                                              │
  ├─ prognosis                                   │
  ├─ treatment                                   │
  ├─ MRD                                         │
  └─ germline                                    │
  │                                              │
  ▼                                              │
typed decision + surfaced fact + reason          │
  │                                              │
  └──────────── evidence alignment ◄─────────────┘
                    │
                    ▼
             locked cited ledger
                    │
                    ▼
               prose synthesis
                    │
                    ▼
           sentence ↔ fact matching
                    │
                    ▼
          deterministic citation render
```

### CMC invariant

Authoritative CMC is never model-authored. Python calls `vocab.preferred_case_major_category()` for every active WHO5 `schema_disease` and takes the ordered union. ICC never participates. `bootstrap_cmcs` exist only for first-pass retrieval.

If WHO5 changes the CMC set, the next diagnosis pass receives diagnosis cards from all CMCs encountered in that run. Once WHO5 stabilises, historical CMCs are audit-only and downstream retrieval uses the final set.

### Concurrent diagnoses

WHO5 can return multiple rows (`DX1`, `DX2`, ...). Prognosis and MRD are decided per `variant × diagnosis`; treatment is decided per `gene × diagnosis`. Retrieved cards record `matched_diagnosis_ids`, and evidence alignment refuses a card that was retrieved only for another concurrent disease context.

### ICC independence

The ICC pass receives the structured case, bootstrap diagnostic evidence and assay scope only. It is frozen before WHO5 runs and is not exposed to WHO5 or downstream tasks. It re-enters only during final fact/evidence assembly and prose synthesis.

## Generic validated model task engine

Structured-output repair is split into two workflow-neutral layers:

- `scripts/core/syntax_repair/` repairs YAML/JSON serialization only;
- `scripts/core/validated_model_task.py` owns structured path-specific validation issues and clinical/schema retry instructions.

For YAML/JSON model output, v3 first parses the artifact, applies only conservative deterministic representation cleanup, then (only if syntax is still invalid) gives a compact syntax-only prompt to the same configured model. The syntax repair model receives the parser error and broken artifact, not the original clinical prompt/case/cards, and is explicitly forbidden to change facts. Two syntax-only attempts are allowed. Every repaired candidate must preserve the complete recoverable lexical-content multiset plus protected numeric/ID/card-tag tokens. A repair that changes content is rejected.

If both syntax-only attempts fail, one short same-answer reserialization request is tried before the workflow falls back to the normal task retry. Syntax-repair attempts do not consume the ordinary clinical retry budget and are logged separately under `model_steps/NNN_<call>/syntax-repair/`. JSON and YAML use format-specific adapters; plain Markdown model operations bypass this layer.

Each clinical proforma retains its own validator in `runtime.py`. This boundary lets every scheduler share syntax recovery without duplicating clinical validation machinery.

## Declarative schedulers

Terraced-v3 implements five interchangeable schedulers: `domain`, `evidence-first`, `variant-centric`, `global-ledger`, and `adaptive-microtask`. Each scheduler is a `schedulers/<id>/scheduler.yaml` information-flow specification plus optional local prompt assets, interpreted by one core scheduler engine; there are no scheduler-specific Python runners. Select one at setup with `--scheduler`; the choice is persisted in the run state. All schedulers must converge on the same four canonical downstream `FINAL_STATE.yaml` artifacts, so validation, evidence alignment and reporting are scheduler-independent. Use `scheduler-check` and `scheduler-plan` for development; see `schedulers/README.md` for the YAML/prompt contract.

## Invariant detected-variant sentence

Case structuring creates one source-faithful `detected_variants_summary` sentence listing every detected NGS variant in case order, including supplied gene, HGVS nomenclature and VAF. It is outside scheduler logic and outside prose synthesis. Final rendering prepends the exact stored sentence to `report-final.md`, so no scheduler or model can omit or paraphrase it.

## Evidence → prose

A surfaced conclusion contains:

```text
decision → fact → reason → verified card citation
```

Candidate card tags returned by the clinical model are not trusted. A separate semantic alignment pass verifies which cards support the reason sufficiently to justify the fact. Prose is then generated from locked facts only. A final v1-style semantic pass maps every report sentence back to one or more locked facts, and citations are inherited deterministically from that mapping.

## Run-directory layout

Terraced-v3 keeps the run root intentionally sparse. `case.md` is copied there as the immutable true case input. Generated working state lives under `intermediates/`; model-call audit material lives under `model_steps/`; genuine deliverables and operational run outputs remain at root.

Both generated namespaces use three-digit directories allocated in actual creation order within that namespace:

```text
<run>/
├── case.md
├── model_steps/
│   ├── 001_structure_case/
│   ├── 002_icc_independent/
│   ├── 003_who5_01_main/
│   └── ...
├── intermediates/
│   ├── 001_setup/
│   ├── 002_run_state/
│   ├── 003_structured_case/
│   ├── 004_card_identity/
│   ├── 005_icc_evidence/
│   ├── 006_icc_diagnosis/
│   ├── 007_who5_diagnosis/
│   └── ...
├── report-final.md
├── terraced-v3-debug.zip
├── <validation-marking-package>.zip   # validation modes only
├── workflow.json
└── workflow.log
```

The numbers are not hard-coded stage numbers. If a diagnosis requires extra WHO5 passes or a scheduler creates extra tasks, the directory sequence reflects what was actually generated. Numbering is independent within `model_steps/` and `intermediates/`. Syntax-repair artifacts stay inside their owning numbered model-step directory rather than consuming another top-level sequence number.

## Audit files

Power users should inspect the numbered `intermediates/*_who5_diagnosis/ROUTING.json`, domain `*_state/FINAL_STATE.yaml` files and `*_fact_ledger/fact-ledger-cited.yaml`. Developers should additionally inspect `model_steps/`, the WHO5 pass subdirectories, scheduler-specific intermediates and `workflow.log`.

## Prototype limitations

This build intentionally keeps the clinical schemas compact. The adaptive scheduler currently uses a simple high-impact-cell escalation rule rather than a learned uncertainty score; there is no separate card→reason / reason→fact entailment reviewer, and clone assignment remains disease-scoped rather than independently inferred when one variant could belong to multiple concurrent neoplasms.
