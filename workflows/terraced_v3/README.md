# Terraced v3

Terraced v3 separates **clinical reasoning**, **evidence trust**, and **report wording**. The normal user-facing configuration unit is a **pipeline**. A pipeline chooses one declarative scheduler for each of three invariant phases and binds every model role to a provider/model/token cap.

## Quickstart

Default self pipeline:

```bash
python workflows/terraced_v3/step.py setup \
  --mode nel-validate-brief --case-id 1 --pipeline self
python workflows/terraced_v3/step.py run --work-dir <printed-work-dir>
```

Normal report mode:

```bash
python workflows/terraced_v3/step.py setup \
  --mode ngs-report --case-file case.md --pipeline self
python workflows/terraced_v3/step.py run --work-dir <printed-work-dir>
```

Shipped pipelines are `self`, `lmstudio`, and `openrouter`.

```bash
python workflows/terraced_v3/step.py pipelines
python workflows/terraced_v3/step.py pipeline-check --pipeline lmstudio
python workflows/terraced_v3/step.py pipeline-plan --pipeline openrouter
```

For development, one scheduler phase can be overridden without cloning the pipeline:

```bash
python workflows/terraced_v3/step.py setup \
  --mode nel-validate-brief --case-id 1 --pipeline self \
  --diagnosis-scheduler minimal-diagnosis \
  --ptbg-scheduler evidence-first \
  --summarization-scheduler minimal-summarization
```

The resolved pipeline and scheduler overrides are snapshotted into the run intermediates at setup.

## Architecture

```text
case.md
  │
  ▼
[C] structure immutable case + stable variant IDs
  │
  ▼
[S-DX] diagnosis scheduler
  │       blind ICC + WHO5 reasoning topology defined by YAML
  ▼
[C] validate diagnosis contract; derive CMC only from WHO5
  │
  ▼
[S-PTBG] prognosis/treatment/biomarker/germline scheduler
  │       decision + surfaced fact + reason + candidate card tags
  ▼
[C] validate canonical PTBG states
  │
  ▼
[C] fact/reason ↔ card semantic alignment
  │
  ▼
[C] locked cited fact ledger
  │
  ▼
[S-SUM] summarization scheduler
  │       final report sentences paired to fact IDs/card tags
  ▼
[C] validate sentence/fact/card provenance
  │
  ├─► deterministic sentence-card-interpretations.yaml
  │
  ▼
[C] prepend invariant detected-variant sentence + render citations
  │
  ▼
report-final.md
```

`C` is core; `S-DX`, `S-PTBG`, and `S-SUM` are independently selectable declarative schedulers.

## Invariant scheduler contracts

Schedulers may alter **how** a phase reaches its answer, but not what crosses the phase boundary.

- Diagnosis output: `icc`, `who5`, `routing`.
- PTBG output: `prognosis`, `treatment`, `biomarker`, `germline` canonical states.
- Summarization output: ordered sentence rows containing `sentence_id`, `domain`, `sentence`, paired `fact_ids`, and inherited `card_tags`.

Core validates every boundary before the next phase starts.

### Diagnosis and CMC

CMC is never model-authored. Core derives the ordered set of active CMCs from validated WHO5 `schema_disease` values. ICC never controls routing.

The shipped `default-diagnosis` scheduler reproduces the protected v3 diagnosis flow: blind ICC; WHO5 initial pass; cumulative old+new CMC evidence after routing changes; targeted reconsideration; adversarial confirmation; bounded oscillation protection. `minimal-diagnosis` is a small developer example demonstrating the same output contract with less safety depth.

Concurrent WHO5 diagnoses are supported. Downstream evidence and decisions remain diagnosis-scoped so one alteration can be considered separately in overlapping diseases.

### PTBG

Five PTBG schedulers are shipped under `schedulers/ptbg/`:

- `domain`
- `evidence-first`
- `variant-centric`
- `global-ledger`
- `adaptive-microtask`

They differ in model-call topology only. All must publish the same four canonical clinical states.

### Summarization

The summarization scheduler receives the **locked cited fact ledger**, not raw case/card reasoning context. It may change drafting/review topology but cannot change the accepted clinical facts or citation trust rules.

`default-summarization` reproduces the current two-step behaviour: prose draft followed by sentence↔fact semantic alignment, with one complete rewrite if accepted facts are omitted. `minimal-summarization` is a one-call developer example that directly emits sentence/fact pairs.

After the scheduler completes, core deterministically resolves each sentence's paired card tags to the exact drawn card interpretations and writes `sentence-card-interpretations.yaml`. This intermediate is not another model judgement.

## Pipelines

Pipeline YAMLs live under `pipelines/`. They contain **composition and model configuration only**:

```yaml
pipeline:
  id: self
schedulers:
  diagnosis: default-diagnosis
  ptbg: domain
  summarization: default-summarization
models:
  structure: {model: self, temperature: 0.0, max_tokens: 16384}
  diagnosis: {model: self, temperature: 0.0, max_tokens: 32768}
  ptbg: {model: self, temperature: 0.0, max_tokens: 32768}
  evidence_alignment: {model: self, temperature: 0.0, max_tokens: 16384}
  summarization: {model: self, temperature: 0.0, max_tokens: 16384}
  summarization_review: {model: self, temperature: 0.0, max_tokens: 16384}
  syntax_repair: {model: self, temperature: 0.0, max_tokens: 8192}
```

See `pipelines/README.md` for provider fields and pipeline development.

## Scheduler development

Schedulers are YAML instruction sets interpreted by one generic Python engine. Scheduler-specific model instructions live beside the YAML in `prompts/`; scheduler folders contain no Python runners.

```bash
python workflows/terraced_v3/step.py schedulers
python workflows/terraced_v3/step.py schedulers --phase diagnosis
python workflows/terraced_v3/step.py scheduler-check --phase ptbg --scheduler evidence-first
python workflows/terraced_v3/step.py scheduler-plan --phase summarization --scheduler default-summarization
```

See `schedulers/README.md` for the YAML DSL, invariant phase interfaces, prompt templates, static prompt-fragment injection, previous-model-output injection, registered deterministic primitives, and how to add a scheduler.

## Evidence and citation integrity

Clinical schedulers may return candidate card tags, but candidate citations are not trusted. Core performs semantic fact/reason↔card alignment and freezes a cited fact ledger. Summarization may only pair report sentences to those accepted facts; core requires the sentence card tags to equal the citations inherited from the paired facts.

Thus scheduler experimentation cannot weaken citation guarantees.

## Structured-output repair

`scripts/core/syntax_repair/` is the generic YAML/JSON syntax fixer used before task-specific validation. It performs conservative deterministic representation cleanup, then at most two compact syntax-only model repairs. The repair model sees the parser error and malformed artifact, not the clinical context, and is forbidden to change informational content. Content-preservation checks reject changed facts. Syntax-repair attempts do not consume ordinary clinical retry attempts.

Bare 12-character card hashes in known card-tag fields are deterministically canonicalized to `[card:<hash>]` before validation when the hash exactly matches a card supplied to that task; an undrawn hash remains invalid.

## Invariant detected-variant sentence

Case structuring creates a source-faithful sentence listing every detected NGS variant in case order with supplied gene, HGVS and VAF. It is outside all schedulers and is deterministically prepended to `report-final.md`.

## Run-directory layout

```text
<run>/
├── case.md                         # immutable true input
├── model_steps/                    # numbered model-call audit trail
│   ├── 001_.../
│   └── ...
├── intermediates/                  # numbered workflow state/artifacts
│   ├── 001_setup/
│   ├── 002_run_state/
│   └── ...
├── report-final.md
├── terraced-v3-debug.zip
├── <validation-marking-package>.zip   # validation modes only
├── workflow.json
└── workflow.log
```

Numbers reflect actual creation order independently within `model_steps/` and `intermediates/`. Syntax-repair files remain nested inside their owning model step.

Useful intermediates include the resolved pipeline snapshot, frozen diagnosis/routing state, canonical PTBG states, cited fact ledger, canonical summary YAML, and `sentence-card-interpretations.yaml`.

## Main risks / prototype limitations

`minimal-diagnosis` intentionally lacks the safety depth of `default-diagnosis` and is for development only. The adaptive PTBG scheduler still uses a simple deterministic escalation policy. Clone assignment is disease-scoped rather than independently inferred when one variant may belong to more than one concurrent neoplasm. Pipeline YAML is intentionally not a programming language; genuinely new deterministic behaviour should be added as a reusable tested core primitive rather than arbitrary executable YAML.
