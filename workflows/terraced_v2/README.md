# terraced-v2

`terraced-v2` is a YAML-driven NGS reporting workflow that combines the diagnosis-state mechanics developed in `terraced-v1/diagnosis_lab` with the provider abstraction, evidence rendering, CLI lifecycle, logging, and downstream terrace concepts of `terraced-v1`.

It is a new workflow. It does **not** replace or modify `terraced-v1` or `terraced-v1/diagnosis_lab`.

The central design is:

```text
case.md
  ↓
case.json
  ↓
WHO5/ICC diagnosis terraces
  ↓
freeze diagnosis boundary
  ↓
germline terraces
  ↓
prognosis terraces
  ↓
biomarker / MRD terraces
  ↓
treatment terraces
  ↓
final report
```

Execution is intentionally serial. This avoids relying on parallel model capacity and lets treatment consume accepted facts from the earlier downstream domains where appropriate.

The canonical pipeline definition is `workflow.yaml`. Python implements named deterministic/model modules, but does not independently define a second provider-specific workflow.

---

# Quickstart

Run commands from the repository root.

## Frontier / SKILL harness

Select v2 explicitly:

```text
ngs-report --terraced-v2
nel-demo example 1 --terraced-v2
nel-validate 1C --terraced-v2
nel-validate-function 3B --terraced-v2
nel-validate-brief 8 --terraced-v2
```

The root `SKILL.md` routes to this directory's `SKILL.md`.

`--terraced` remains an alias for `terraced-v1`; v2 is deliberately opt-in through `--terraced-v2`.

For ChatGPT/session execution the normal settings are:

```text
model profile:   self
terrace profile: frontier
```

With model profile `self`, each model operation is packaged by the CLI. The runner exits with code `10` and prints:

```text
HANDOFF=<operation-id>
PROMPT=<path>
OUTPUT=<path>
```

The session model reads only the packaged prompt, writes only the requested output, then reruns the same `run` command. The same `workflow.yaml`, prompts, validators, card draws, context boundaries and output contracts are used by all providers.

## Python environment

Create the repository environment once:

```bash
python3 -m venv .env
.env/bin/python -m pip install -r requirements.txt
```

Use `.env/bin/python` in the examples below.

## Provider defaults

Show the current effective provider and terrace profiles:

```bash
.env/bin/python workflows/terraced_v2/step.py provider
```

Persist defaults for future runs:

```bash
.env/bin/python workflows/terraced_v2/step.py provider lmstudio balanced
```

or:

```bash
.env/bin/python workflows/terraced_v2/step.py provider ollama deliberate
.env/bin/python workflows/terraced_v2/step.py provider openrouter balanced
.env/bin/python workflows/terraced_v2/step.py provider self frontier
```

This writes local settings to `workflows/terraced_v2/settings.json`. A one-run `setup --model-profile ... --terrace-profile ...` override takes precedence.

## Direct CLI: clinical case

```bash
.env/bin/python workflows/terraced_v2/step.py setup \
  --mode ngs-report \
  --case-file case.md \
  --project
```

The first output line is the work directory. Then run:

```bash
.env/bin/python workflows/terraced_v2/step.py run --work-dir <work-dir>
```

Example using LM Studio without changing persistent defaults:

```bash
.env/bin/python workflows/terraced_v2/step.py setup \
  --mode ngs-report \
  --case-file case.md \
  --model-profile lmstudio \
  --terrace-profile balanced \
  --project

.env/bin/python workflows/terraced_v2/step.py run --work-dir <work-dir>
```

## Demo and validation modes

Bundled demo:

```bash
.env/bin/python workflows/terraced_v2/step.py setup \
  --mode nel-demo \
  --example 1 \
  --project

.env/bin/python workflows/terraced_v2/step.py run --work-dir <work-dir>
```

Named validation case:

```bash
.env/bin/python workflows/terraced_v2/step.py setup \
  --mode nel-validate \
  --case-id 1C \
  --project

.env/bin/python workflows/terraced_v2/step.py run --work-dir <work-dir>
```

Functional and brief validation use the corresponding modes:

```text
nel-validate-function
nel-validate-brief
```

Validation runs package the final report for external marking. `terraced-v2` does **not** mark its own output.

---

# Architecture

## 1. YAML is the canonical workflow

`workflow.yaml` defines the ordered pipeline:

```text
1  structure
2  corpus
3  diagnosis
4  diagnosis_report
5  germline
6  prognosis
7  biomarker
8  treatment
9  finalise
```

Each stage declares a module and, where relevant, its clinical domain, evidence category, permitted upstream context and outputs.

The runner in `step.py` maps those module names to Python implementations. The YAML therefore owns orchestration while Python owns deterministic logic such as validation, card identity, retrieval, rendering, packaging and provider transport.

This separation is intentional. Provider selection must not produce a different clinical pipeline.

## 2. `case.md` and `case.json`

`input/case.md` is the immutable human-authored source case.

The first model operation structures it once into `input/case.json`. After that point the raw markdown is audit-only and subsequent model stages use the structured JSON state.

`case.json` contains exactly:

```text
provisional_cmcs
provisional_disease
genes
detected_variants_summary
case_facts
```

The case facts preserve patient-level observations as structured source state. The genes are fixed at case structuring and are used for deterministic card retrieval throughout the run.

The workflow deliberately avoids injecting both raw `case.md` and structured `case.json` into every later call. This reduces duplicate context and prevents later stages from repeatedly reinterpreting the original prose.

## 3. Deterministic whole-corpus card identity

Before clinical terraces begin, the workflow initializes a whole-corpus identity manifest:

```text
evidence/card-identity-manifest.json
```

Every corpus card receives one deterministic 12-hex runtime identity before retrieval/filtering. The identity is therefore stable within the run and is not dependent on which cards happen to be drawn for a particular terrace.

Clinical reasoning does not choose citations. Card tags are used only by later evidence-alignment operations.

## 4. Diagnosis terraces

Diagnosis uses an evolving state derived from the `diagnosis_lab` design.

Each diagnosis terrace works on one complete current state:

```yaml
provisional_cmcs:
  - AML

diagnoses:
  - schema_disease: AML
    WHO5:
      status: established
      diagnosis: AML with defining genetic abnormality
    ICC:
      status: established
      diagnosis: AML with defining genetic abnormality
    materially_different: false

facts:
  - fact: "..."
    reason: "..."

uncertainties:
  - uncertainty: "..."
    reason: "..."
```

The permitted classifier statuses are:

```text
established
indeterminate
not_established
not_applicable
```

Terraces are progressive reconsideration rather than append-only questioning. For each new question the preferred operations are:

```text
delete → modify → merge → leave unchanged → add
```

This avoids retaining superseded diagnostic reasoning merely for historical completeness.

### WHO5 and ICC roles

WHO5 and ICC are derived independently but stored together for each disease process.

WHO5 is authoritative for:

- the patient-level assigned diagnosis;
- `schema_disease`; and
- downstream disease routing.

ICC is comparator-only. An ICC label cannot replace WHO5 routing, and ICC-only `MDS/AML` is not accepted as a WHO5 routing disease.

### Concurrent pathology

Multiple paired diagnosis rows are allowed when there is genuine evidence of concurrent disease processes.

Different WHO5 and ICC names for the same disease process are **not** treated as concurrent pathology; they remain one paired row.

### Evolving CMC and diagnosis evidence

The diagnostic CMC is an evolving retrieval scaffold, not the final diagnosis.

At each diagnosis terrace, evidence drawing is based on:

```text
fixed case genes
+
current provisional CMC state
+
diagnosis evidence category
```

Diagnosis retrieval can therefore expand when a later terrace seriously entertains a new disease family, without changing the fixed molecular observations extracted from the case.

Diagnosis evidence includes diagnostic cards and the gene-matched predisposition evidence needed for diagnosis-sensitive reasoning, following the diagnosis-lab mechanics.

## 5. Final diagnosis synthesis

The final diagnostic terrace is deliberately separated from evidence citation.

It consolidates the reviewed diagnostic state into the final paired WHO5/ICC output while preserving protected classifier state. It produces report-facing diagnostic facts and uncertainties with provenance back to the pre-final diagnostic state.

The authoritative diagnostic state is:

```text
diagnosis/FINAL_OUTPUT.yaml
```

The diagnosis report stage then grounds and aligns the report-facing diagnostic content against the permitted diagnosis evidence and writes:

```text
diagnosis/FINAL_ALIGNED.yaml
diagnosis/FINAL_REPORT.md
```

## 6. The diagnosis boundary

Diagnosis is frozen before the downstream domains begin.

Only the following diagnostic context is exposed downstream:

```text
CMC
established WHO5 diagnosis rows
accepted diagnosis facts
```

Diagnostic uncertainties do **not** cross the boundary.

An indeterminate WHO5 candidate label is not promoted into downstream diagnostic context. When no WHO5 diagnosis is established, the still-explicit CMC can continue to provide broad retrieval routing without converting the indeterminate label into an accepted premise.

Downstream stages cannot mutate diagnosis. If a later domain discovers a genuine material inconsistency with accepted upstream state, it records an `upstream_issue` rather than silently changing the diagnosis.

## 7. Serial downstream domains

The execution order is:

```text
germline
→ prognosis
→ biomarker / MRD
→ treatment
```

This is an execution order, not an assertion that every stage consumes every preceding stage.

The permitted information dependencies are explicit in `workflow.yaml`.

### Germline

Germline runs immediately after diagnosis because germline interpretation is diagnosis-like: it may depend on age, family history, molecular findings, disease context and the distinction between overt disease and predisposition.

It receives:

```text
case.json
+ CMC
+ established WHO5 diagnosis
+ accepted diagnosis facts
+ germline evidence
```

It does not receive diagnostic uncertainties.

### Prognosis

Prognosis receives:

```text
case.json
+ CMC
+ established WHO5 diagnosis
+ accepted diagnosis facts
+ prognosis evidence
```

It does not automatically consume germline conclusions merely because germline executed first.

### Biomarker / MRD

The biomarker stage carries the MRD questions inherited from the v1 clinical question set.

It receives:

```text
case.json
+ CMC
+ established WHO5 diagnosis
+ accepted diagnosis facts
+ biomarker evidence
```

The questions distinguish prospective marker suitability at diagnosis from interpretation of an actual follow-up MRD result.

### Treatment

Treatment runs last because it is the one downstream stage deliberately permitted to use established conclusions from multiple prior domains.

It receives:

```text
case.json
+ diagnosis context
+ accepted germline facts
+ accepted prognosis facts
+ accepted biomarker facts
+ treatment evidence
```

Only accepted `facts` propagate. Downstream `uncertainties` never silently become premises for another domain.

## 8. Downstream terrace state

Each downstream domain maintains one evolving state:

```yaml
facts:
  - fact: "..."
    reason: "..."

uncertainties:
  - uncertainty: "..."
    reason: "..."

upstream_issues:
  - issue: "..."
    reason: "..."
```

All three lists may be empty.

`facts` are accepted patient-level conclusions suitable for report generation.

`uncertainties` are clinically material unresolved issues local to that domain. They may appear in that domain's report, but are never exposed as premises to another downstream stage.

`upstream_issues` are exceptional audit/review flags. They are not report prose and do not mutate upstream state.

## 9. Stage-local evidence

Evidence remains category-local rather than giving every model call the complete corpus and asking the model to decide relevance.

The intended mapping is:

```text
diagnosis  → diagnosis evidence
germline   → germline evidence
prognosis  → prognosis evidence
biomarker  → biomarker evidence
treatment  → treatment evidence
```

Downstream retrieval uses the accepted WHO5 routing diseases and case genes with the narrow disease/gene retrieval semantics inherited from `terraced-v1`.

Clinical terraces see rendered evidence but are instructed not to emit card IDs or citations.

## 10. Evidence alignment

After a downstream domain finishes, a separate evidence-alignment model operation receives the immutable final domain state plus only that domain's permitted evidence.

It may add only:

```yaml
citation: "[card:0123456789ab]"
```

or:

```yaml
citation: null
```

It must preserve `fact`, `uncertainty` and `reason` text character-for-character.

Case-derived observations and limitations may correctly receive `citation: null`. A card should be attached only when it directly supports the complete stated reason at the claimed strength.

The aligned artifact is:

```text
<domain>/FINAL_ALIGNED.yaml
```

and deterministic code renders:

```text
<domain>/FINAL_REPORT.md
```

`upstream_issues` remain audit-only and are deliberately omitted from evidence alignment/report rendering.

## 11. Final report

Final report section order is independent of execution order and is configured in `workflow.yaml`.

The current report order is:

```text
diagnosis
prognosis
treatment
biomarker / MRD
germline
```

The already-aligned domain reports are concatenated into a cited draft. Deterministic citation rendering then resolves runtime card tags against the combined evidence set and writes:

```text
report-final.md
```

No model is asked to re-summarize or reinterpret all clinical domains during finalization.

---

# Terrace questions and grouping

`questions.yaml` is the canonical v2 clinical question configuration.

It contains:

1. the ordered questions for each domain; and
2. execution profiles that group those questions into model calls.

Current domains are:

```text
diagnosis
germline
prognosis
biomarker
treatment
```

The downstream question intent is borrowed from the mature `terraced-v1` question set, while diagnosis uses the diagnosis-lab-style paired WHO5/ICC state.

## Execution profiles

Three profiles are provided:

| Profile | Grouping style | Intended use |
|---|---|---|
| `frontier` | larger question groups | strong session/frontier models; fewer calls |
| `balanced` | intermediate grouping | capable local models |
| `deliberate` | one question per call | weaker local models, debugging, evaluation |

Grouping changes the number of model calls, not the clinical questions or their order.

The diagnosis groups are intentionally somewhat more granular even under `frontier`, because diagnosis state changes may affect subsequent card retrieval.

---

# Providers

## One workflow, four transports

Supported model profiles are:

```text
self
lmstudio
ollama
openrouter
```

All four execute the same pipeline. There are no provider-specific clinical branches in `workflow.yaml`.

The provider abstraction changes only how a packaged model operation obtains a completion.

## `self`

`self` is for ChatGPT/session execution.

The Python runner packages the complete bounded operation and exits `10`. The session model executes that operation and writes the requested artifact. Rerunning the same command validates/reuses the artifact and continues.

This makes the session model participate in the same workflow rather than reproducing a separate workflow from prose in `SKILL.md`.

## LM Studio

Default endpoint:

```text
http://localhost:1234/v1
```

Override with:

```text
NEL_LMSTUDIO_BASE_URL
```

The shipped model IDs are examples/defaults and should be changed to match the models actually loaded by the local server.

## Ollama

Default OpenAI-compatible endpoint:

```text
http://localhost:11434/v1
```

Override with:

```text
NEL_OLLAMA_BASE_URL
```

Model names must match locally installed Ollama models.

## OpenRouter

Default endpoint:

```text
https://openrouter.ai/api/v1
```

Set:

```bash
export OPENROUTER_API_KEY='...'
```

The endpoint can be overridden with `NEL_OPENROUTER_BASE_URL`.

## Model roles

`models.json.template` defines four roles:

```text
structure
answer
evidence_alignment
summarisation
```

A local `models.json` overrides `models.json.template` when present. This is the place to change model IDs, endpoints/role bindings, temperature and token limits without changing workflow orchestration.

---

# Configuration files

Repository defaults live in:

```text
workflow.yaml
questions.yaml
models.json.template
settings.json.template
```

Optional local overrides are:

```text
models.json
settings.json
```

`workflow.yaml` and `questions.yaml` are copied into each work directory under `input/` at setup so the exact workflow/question configuration used by the run remains auditable.

`settings.json.template` currently declares structural retry count and a token-budget setting. The v2 runner actively reads `structural_attempts`; evidence rendering currently uses the shared renderer default token budget. The `provider` command creates/updates local `settings.json` with persistent model and terrace profile selections.

---

# Prompt roles

Workflow-local prompts live under `workflows/terraced_v2/prompts/`.

## `structure_case.md`

**Role:** `structure`

Converts immutable `case.md` into canonical `case.json` without performing the final diagnosis.

## `diagnosis_terrace.md`

**Role:** `answer`

Runs the evolving paired WHO5/ICC diagnostic state. Questions are stimuli for reconsideration of the whole state rather than independent answers.

## `diagnosis_report_synthesis.md`

**Role:** `summarisation`

Converts the reviewed pre-final diagnostic state into final report-facing diagnosis facts/uncertainties while preserving protected diagnostic state and source-state provenance.

## `diagnosis_report_reasons.md`

**Role:** `evidence_alignment`

Grounds the report-facing diagnostic reasons against the permitted diagnosis evidence without changing the underlying diagnostic meaning.

## `diagnosis_report_alignment.md`

**Role:** `evidence_alignment`

Adds permitted runtime evidence tags to the immutable diagnosis report facts/uncertainties.

## `downstream_terrace.md`

**Role:** `answer`

Runs one evolving state for germline, prognosis, biomarker/MRD or treatment using only the structured case, explicitly permitted upstream state, current domain evidence and prior turns from the same domain.

## `domain_alignment.md`

**Role:** `evidence_alignment`

Copies downstream facts/uncertainties exactly and adds only direct evidence dispositions.

---

# Conversation and model-call mechanics

The CLI owns the canonical context for every model operation. Provider-side hidden conversation state is not authoritative.

For each downstream domain the effective context is reconstructed from:

```text
immutable case.json
+ explicitly permitted upstream context
+ assay scope
+ current domain evidence
+ prior turns from this domain
+ current terrace question group
```

Each call directory also records model-call inputs such as:

```text
INPUT_context.md
INPUT_questions.md
INPUT_previous_state.yaml
INPUT_cards.json
OUTPUT_state.yaml
```

The exact packaged provider operation is stored under:

```text
state/model-steps/<operation-id>/
```

including `prompt.md`, `messages.json`, attempt outputs/validation messages and the final deterministic validation record.

This makes runs resumable and provides an audit trail independent of provider-side chat history.

---

# Validation and repair

Every model artifact is deterministically validated before the workflow proceeds.

For direct providers, validation failure causes the next attempt to receive the previous output plus the complete deterministic validator message and an instruction to repair only the reported defects.

The status output is:

```text
answering
retry 1/9
retry 2/9
...
```

The maximum structural attempts come from `settings.json` / `settings.json.template`.

For `self`, an invalid existing output produces a new correction handoff containing the validator error. The session model corrects the bounded artifact and reruns the same command.

Completed artifacts are revalidated and reused, which is the basis of resume behaviour.

---

# Logging and terminal output

CLI status messages follow the v1 elapsed-time format:

```text
[ 0000 ] - Stage 1 of 9 — Structure immutable case state
[ 0012 ] -   structure-case: answering
[ 0024 ] - Stage 1 of 9 — complete
```

Elapsed seconds are measured from the start of the current command invocation.

The complete stdout/stderr stream is appended to:

```text
workflow.log
```

The terminal intentionally masks routine low-value chatter including:

- low-level retrieval messages;
- renderer status messages; and
- routine `validation pass` messages.

Those messages remain in `workflow.log` for audit/debugging.

---

# Work-directory layout

New project work directories use readable timestamped names rather than random hashes, for example:

```text
temp/terraced-v2-ngs-report-case-20260821T121530Z/
```

The exact label depends on mode/case identifier.

The root is kept relatively compact. Shared state is nested and each clinical domain owns its own call folders.

Typical layout:

```text
<work-dir>/
├── input/
│   ├── case.md
│   ├── case.json
│   ├── ngs-panel-scope.md
│   ├── case-major-categories.json
│   ├── allowed-schema-diseases.json
│   ├── workflow.yaml
│   └── questions.yaml
├── evidence/
│   ├── card-identity-manifest.json
│   ├── diagnosis-bundle.json
│   ├── evidence-diagnosis.md
│   ├── germline-bundle.json
│   ├── evidence-germline.md
│   ├── prognosis-bundle.json
│   ├── evidence-prognosis.md
│   ├── biomarker-bundle.json
│   ├── evidence-biomarker.md
│   ├── treatment-bundle.json
│   ├── evidence-treatment.md
│   └── ...
├── state/
│   ├── terraced-v2-run.json
│   └── model-steps/
│       └── <operation-id>/
├── synthesis/
│   └── report-cited.md
├── diagnosis/
│   ├── call_01_.../
│   ├── ...
│   ├── FINAL_OUTPUT.yaml
│   ├── FINAL_FACTS.yaml
│   ├── FINAL_ALIGNED.yaml
│   └── FINAL_REPORT.md
├── germline/
│   ├── call_01_.../
│   ├── FINAL_STATE.yaml
│   ├── FINAL_ALIGNED.yaml
│   └── FINAL_REPORT.md
├── prognosis/
│   └── ...
├── biomarker/
│   └── ...
├── treatment/
│   └── ...
├── workflow.json
├── workflow.log
├── report-final.md
└── terraced-v2-debug.zip
```

Exact evidence support files may vary by stage, but the domain and shared-state separation is stable.

---

# Important outputs

## End user

The main clinical output is:

```text
report-final.md
```

For validation modes, the corresponding externally markable package is also created in the work directory.

## Power user / clinical reviewer

The most useful intermediate artifacts are:

```text
input/case.json

diagnosis/FINAL_OUTPUT.yaml
diagnosis/FINAL_FACTS.yaml
diagnosis/FINAL_ALIGNED.yaml

germline/FINAL_STATE.yaml
germline/FINAL_ALIGNED.yaml

prognosis/FINAL_STATE.yaml
prognosis/FINAL_ALIGNED.yaml

biomarker/FINAL_STATE.yaml
biomarker/FINAL_ALIGNED.yaml

treatment/FINAL_STATE.yaml
treatment/FINAL_ALIGNED.yaml
```

These separate the model's final clinical state from the later evidence dispositions.

## Developer / audit

Useful debugging artifacts include:

```text
workflow.log
state/terraced-v2-run.json
state/model-steps/
evidence/card-identity-manifest.json
<domain>/call_XX_*/
terraced-v2-debug.zip
```

`terraced-v2-debug.zip` packages the non-zip run artifacts for portable inspection.

---

# Manual / stage execution

The normal command is:

```bash
.env/bin/python workflows/terraced_v2/step.py run --work-dir <work-dir>
```

For development/debugging, one YAML stage can be selected explicitly:

```bash
.env/bin/python workflows/terraced_v2/step.py run \
  --work-dir <work-dir> \
  --stage diagnosis
```

Valid stage IDs are the IDs in `workflow.yaml`:

```text
structure
corpus
diagnosis
diagnosis_report
germline
prognosis
biomarker
treatment
finalise
```

A manually selected stage does not magically construct missing prerequisites. Use stage execution for debugging/resume only when the required upstream artifacts already exist.

A temporary model-profile override is also available on `run`:

```bash
.env/bin/python workflows/terraced_v2/step.py run \
  --work-dir <work-dir> \
  --profile openrouter
```

The work directory remains bound to the same workflow; provider transport does not change its pipeline definition.

---

# Design invariants

`workflow.yaml` records the important v2 invariants explicitly:

```text
raw case source                  = input/case.md
canonical machine case           = input/case.json
case.md after structuring         = audit only
diagnostic authority              = WHO5
ICC role                          = comparator only
downstream diagnostic context     = CMC + WHO5 + accepted facts
cross-domain uncertainty          = prohibited
downstream diagnosis mutation     = prohibited
provider-specific pipeline branch = prohibited
whole-corpus deterministic IDs    = required
marking                           = package only
```

These are architectural constraints, not merely prompt suggestions.

---

# Relationship to terraced-v1 and diagnosis_lab

`terraced-v2` intentionally borrows from both predecessors without changing them.

From `terraced-v1` it retains useful ideas including:

- one provider abstraction for session and direct models;
- local-model terrace grouping profiles;
- category-specific evidence retrieval/rendering;
- explicit model roles;
- deterministic validation/repair loops;
- elapsed-time CLI messages;
- complete workflow logging;
- timestamped project work directories;
- validation packaging; and
- the mature downstream clinical question intent.

From `terraced-v1/diagnosis_lab` it adopts the newer diagnostic concepts including:

- paired WHO5/ICC diagnostic state;
- evolving CMC across diagnostic terraces;
- facts and uncertainties as explicit state;
- deterministic whole-corpus card identity;
- terrace-local diagnostic card draws; and
- a protected final diagnostic synthesis step.

The resulting v2 architecture extends the same stateful terrace idea into germline, prognosis, biomarker/MRD and treatment rather than returning to the older v1 category flow after diagnosis.

---

# Customisation

## Change clinical questions

Edit:

```text
workflows/terraced_v2/questions.yaml
```

Question IDs must remain unique within a domain, and every execution profile must cover each domain's questions exactly once and in canonical order.

## Change grouping without changing questions

Modify only the `execution_profiles` section of `questions.yaml`.

This is the preferred way to adapt the workflow to models with different context/reasoning ability while keeping clinical content unchanged.

## Change model/provider configuration

Copy:

```bash
cp workflows/terraced_v2/models.json.template workflows/terraced_v2/models.json
```

Then edit the local file.

Use this for model IDs, role bindings, endpoints, temperatures and token limits.

## Change retry/token settings

A local `settings.json` may override `settings.json.template`.

The `provider` command also writes the selected persistent model and terrace profiles there.

## Change pipeline orchestration

Edit `workflow.yaml` only when intentionally changing workflow architecture.

Do not introduce provider-specific stage ordering or hidden Python-only clinical branches. New module names also require a corresponding implementation in `step.py`.

---

# Risks and current limitations

## Provider equivalence is architectural, not output identity

All providers receive the same declared workflow and contracts, but different models may still produce different clinical reasoning within those contracts. Provider equivalence means equivalent pipeline mechanics, not byte-identical model output.

## Local models remain capacity-sensitive

The workflow is serial partly for local-model reliability, but large evidence/context bundles can still stress smaller models. Use `balanced` or `deliberate` grouping when needed and tune model token limits appropriately.

## Diagnosis is intentionally one-way

Once the diagnosis boundary is frozen, later domains cannot automatically reopen diagnosis. A downstream contradiction is surfaced as an `upstream_issue` for review rather than producing an uncontrolled feedback loop.

## Uncertainty does not propagate

This is deliberate for safety and reasoning hygiene, but it means a clinically important uncertainty must be independently rediscovered by a later domain if it matters there. Only accepted upstream facts are permitted premises.

## Existing corpus/blacklist consistency still matters

Retrieval quality depends on the corpus and blacklist state supplied by the repository. `terraced-v2` does not make inconsistent corpus metadata harmless; corpus-maintenance issues should be repaired at source.

---

# Developer checklist

When changing `terraced-v2`:

1. Preserve `terraced-v1` and `terraced-v1/diagnosis_lab` unless the change explicitly targets them.
2. Keep `workflow.yaml` as the single orchestration source of truth.
3. Keep provider choice below the workflow layer.
4. Preserve raw `case.md`; structure once into `case.json`.
5. Do not propagate diagnostic uncertainty downstream.
6. Do not allow downstream stages to mutate WHO5 diagnosis state.
7. Keep evidence stage-local and deterministically selected.
8. Keep clinical answering separate from evidence alignment.
9. Preserve validator feedback in model repair loops.
10. Keep terminal output concise while retaining complete `workflow.log` auditability.
