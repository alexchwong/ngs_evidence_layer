# terraced-v1

`terraced-v1` is an experimental NGS reporting workflow built around progressive clinical questions (“terraces”). It separates clinical reasoning from citation assignment and uses one CLI engine for both frontier-model execution through `SKILL.md` and direct execution through LM Studio, Ollama, or OpenRouter.

```text
terraced answering
→ fact + reason
→ evidence alignment adds citation where directly supported
→ accepted facts only
→ one report synthesis
→ sentence-to-fact citation inheritance
→ deterministic Vancouver rendering
```

The workflow is additive; `categorical-v1`, `diagnosis-first-v1`, and `legacy-v1` remain separate.

---

# Quickstart

Run commands from the repository root.

## Frontier / SKILL harness

Select the workflow with `--terraced` or `--terraced-v1`:

```text
ngs-report --terraced
nel-demo example 1 --terraced
nel-validate 1C --terraced
nel-validate-function 3B --terraced
```

The root `SKILL.md` routes to this directory's `SKILL.md`. The default frontier settings are:

```text
model profile:   self
terrace profile: frontier
```

## Local configuration

The repository ships versioned configuration templates, while the corresponding working files are local user settings and are Git-ignored:

| Shipped template | Local override |
|---|---|
| `models.json.template` | `models.json` |
| `questions.yaml.template` | `questions.yaml` |
| `settings.json.template` | `settings.json` |

The workflow uses a local override when it exists and otherwise reads the shipped template directly. A fresh clone therefore runs with repository defaults without requiring setup files to be generated.

To customise the workflow, copy only the files you intend to change:

```bash
cp workflows/terraced_v1/models.json.template workflows/terraced_v1/models.json
cp workflows/terraced_v1/questions.yaml.template workflows/terraced_v1/questions.yaml
cp workflows/terraced_v1/settings.json.template workflows/terraced_v1/settings.json
```

Edits to these local files will not appear in `git status`. To propose a new repository default, edit the corresponding `.template` file instead.

The CLI packages each model operation. When profile `self` needs the current session model, the command exits `10` and prints:

```text
HANDOFF=<operation-id>
PROMPT=<path>
OUTPUT=<path>
```

The model reads only the packaged prompt, writes the requested output, and reruns the same command.

## Direct CLI

Create the repository environment once:

```bash
python3 -m venv .env
.env/bin/python -m pip install -r requirements.txt
```

Set the provider and terrace grouping defaults once:

```bash
.env/bin/python workflows/terraced_v1/step.py provider openrouter balanced
```

This writes the validated defaults to the local, Git-ignored `settings.json`. Future
`setup` commands use them automatically. Run `provider` without arguments to show
the current effective defaults:

```bash
.env/bin/python workflows/terraced_v1/step.py provider
```

Example with LM Studio:

```bash
.env/bin/python workflows/terraced_v1/step.py provider lmstudio balanced

.env/bin/python workflows/terraced_v1/step.py setup \
  --mode ngs-report \
  --case-file case.md \
  --project

.env/bin/python workflows/terraced_v1/step.py --all
```

Run a bundled `nel-demo` example:

```bash
.env/bin/python workflows/terraced_v1/step.py setup \
  --mode nel-demo \
  --example 1 \
  --project

.env/bin/python workflows/terraced_v1/step.py --all
```

Run a named `nel-validate` case:

```bash
.env/bin/python workflows/terraced_v1/step.py setup \
  --mode nel-validate \
  --case-id 1C \
  --project

.env/bin/python workflows/terraced_v1/step.py --all
```

For functional validation, use `--mode nel-validate-function` with a functional validation case ID.

Equivalent model profiles are:

```text
lmstudio
ollama
openrouter
```

For OpenRouter:

```bash
export OPENROUTER_API_KEY='...'
```

Provider endpoints, model IDs, token limits, and role bindings are read from local `models.json` when present, otherwise from `models.json.template`.

`setup --model-profile ... --terrace-profile ...` remains available for a one-run
override and takes precedence over the defaults saved by `provider`.

## Terrace grouping profiles

The active question configuration (`questions.yaml`, falling back to `questions.yaml.template`) defines three default execution profiles:

| Profile | Calls per category | Intended use |
|---|---:|---|
| `frontier` | 1 | strong frontier/session models; lowest call count |
| `balanced` | ~2 | local models with moderate reasoning/context ability |
| `deliberate` | 1 per terrace | weaker local models, debugging, evaluation |

Grouping changes only how consecutive questions are batched into calls. The clinical questions and their order do not change.

## Manual steps

The canonical workflow is:

```text
1a  capture case
1b  structure case
2   retrieve broad diagnostic evidence
3   terraced diagnosis
4   diagnosis review + evidence alignment
5   downstream terraced categories
6   facts-only synthesis + final citation alignment + render
7   package/deliver
```

Example:

```bash
.env/bin/python workflows/terraced_v1/step.py 3 --work-dir <work-dir>
```

---

# Architecture

## 1. Capture and provisional CMC

The case is captured and structured into `case-input.json` with:

- one or more provisional case-major categories (`provisional_cmcs`);
- the supplied provisional disease wording;
- detected genes; and
- preserved patient-level facts.

The provisional CMC is a **diagnostic retrieval scaffold only**. It is not the final diagnosis.

## 2. Broad diagnostic retrieval

Initial diagnosis retrieval uses the provisional CMCs and detected genes and includes relevant diagnosis cards plus gene-matched germline/predisposition cards.

This keeps the starting retrieval broad enough to reconsider the supplied clinicopathological diagnosis.

## 3. Terraced diagnosis

A terrace is one ordered reporting question from the active question configuration.

The opening diagnosis questions deliberately ask:

1. what is the most likely diagnosis; and
2. what plausible differentials remain, including whether direct evidence supports concurrent second pathology.

Later questions progressively integrate molecular disease-defining findings, precedence/exclusion rules, competing entities, germline-sensitive interpretations, and the final diagnosis.

Terraces are **progressive reconsideration**. Later questions may add, remove, qualify, or replace earlier conclusions.

If a terrace introduces a credible new provisional CMC, the CLI expands diagnostic retrieval before the next question group while preserving the existing conversation.

Diagnosis must finish with one or more accepted **WHO5** diagnoses:

```yaml
diagnoses:
  - schema_disease: AML
    narrow_diagnosis: AML with mutated NPM1
```

`schema_disease` is the controlled downstream retrieval key. `narrow_diagnosis` is patient-level WHO5 wording.

ICC may inform reasoning, but ICC-only `MDS/AML` is deterministically rejected as the final routing diagnosis.

## 4. Concurrent pathology

Both provisional CMCs and accepted diagnoses may be plural:

```yaml
diagnoses:
  - schema_disease: CML
    narrow_diagnosis: CML, BCR::ABL1-positive
  - schema_disease: MPN
    narrow_diagnosis: JAK2-mutated myeloproliferative neoplasm
```

The workflow does not force primary/secondary labels for genuinely concurrent diseases.

Downstream evidence is retrieved against each accepted diagnosis independently. This prevents broad-category contamination such as APL inheriting generic AML treatment cards or CML inheriting generic MPN treatment cards.

## 5. Downstream categories

After diagnosis is accepted, Step 5 processes:

```text
prognosis → treatment → MRD → germline
```

Each category receives:

- the structured case;
- accepted upstream clinical state;
- assay-scope constraints;
- that category's reporting questions; and
- evidence retrieved using the accepted narrow WHO5 diagnosis or diagnoses.

Terraced answering returns only:

```yaml
- fact: "..."
  reason: "..."
```

One `fact` should contain one clinical idea. `reason` explains why it follows from the case and supplied evidence. Card IDs are deliberately excluded during clinical reasoning.

An empty list is valid when a category has no reportable facts.

## 6. Semantic review and evidence alignment

After a category finishes, a fresh semantic reviewer performs a **high-threshold safety review**. It should fail only for material defects such as:

- contradiction with the case;
- contradiction between facts;
- wrong disease/framework application;
- a materially unmet premise;
- incorrect WHO5 routing; or
- material evidence misinterpretation.

It should not fail merely for citation absence, harmless incompleteness, wording preference, or a scoped absence-of-evidence conclusion without a positive card.

If a material defect is found, the owning terraced conversation resumes and may revise the complete category state.

After semantic acceptance, evidence alignment preserves `fact` and `reason` exactly and adds only `citation`:

```yaml
- fact: "..."
  reason: "..."
  citation: "[card:abcdef]"
```

or:

```yaml
- fact: "..."
  reason: "..."
  citation: null
```

`citation: null` is valid. The aligner must not rescue a claim with a vaguely related card.

## 7. Facts-only synthesis

Once all categories are accepted, the CLI builds `report-facts.yaml` by stripping every `reason` and `citation`.

The summariser therefore receives **facts only**. It does not see corpus cards, reasons, or citation tags.

Its single task is to write concise report prose without introducing a new clinical assertion.

## 8. Final citation alignment

The report is initially uncited.

A deterministic sentence manifest assigns stable IDs while preserving the exact report bytes. A separate model pass returns only an ordered YAML mapping from each sentence ID to accepted fact IDs; it never reproduces the report prose or citation tags:

```yaml
alignments:
  - sentence_id: diagnosis-1
    fact_ids: [diagnosis-1]
```

Deterministic code then inherits the facts' already-aligned citations and inserts each citation disposition into the untouched report draft:

```text
CARD
  → supports REASON
  → justifies FACT
  → maps to REPORT SENTENCE
```

If all matched source facts have `citation: null`, the sentence receives `(no citation required)`.

If a sentence cannot be matched to an accepted fact, the pass returns structured `unmatched_sentences` diagnostics containing each sentence ID, exact text, and reason. The workflow supplies those diagnostics to the next synthesis cycle rather than reopening the clinical terraces.

The citation pass cannot alter report prose or search for new evidence. Removing the deterministically inserted dispositions must recover `report-draft.md` byte-for-byte.

## 9. Deterministic render and packaging

After semantic mapping, deterministic code validates runtime card tags, deduplicates publications, assigns Vancouver numbers, sorts and collapses each displayed citation group into ranges (for example `[3,1,7,2]` becomes `[1-3,7]`), writes `report-final.md`, and invokes the existing repository packaging behaviour.

Supported modes are:

```text
ngs-report
nel-demo
nel-validate
nel-validate-function
```

---

# Prompt roles

Workflow-local prompts live under `prompts/`. The ordered clinical questions live in local `questions.yaml` or, when no override exists, `questions.yaml.template`.

## `prompts/structure_case.md`

**Role:** `structure`

Converts the captured case into `case-input.json`. It preserves case facts, selects provisional retrieval CMCs, and records detected genes without performing final molecular diagnosis.

## `prompts/terrace_answer.md`

**Role:** `answer`

The main clinical reasoning prompt. It runs one or more ordered reporting questions as progressive reconsideration of the complete current category state.

Diagnosis output:

```yaml
provisional_cmcs: [...]
diagnoses: [...]
facts:
  - fact: "..."
    reason: "..."
```

Downstream output is a YAML list of `fact` + `reason` pairs.

## `prompts/semantic_review.md`

**Role:** `semantic_review`

Independent high-threshold reviewer. It returns only pass/fail plus concise material issues and does not rewrite the answer.

## `prompts/repair_category.md`

**Role:** `answer`

Used only after semantic-review failure. It returns a complete replacement category state and may revise conclusions affected by the review finding.

## `prompts/evidence_alignment.md`

**Role:** `evidence_alignment`

Preserves each final `fact` and `reason` and adds only `citation`, using exact runtime card tags where a supplied card directly supports the stated reason. No direct match becomes `citation: null`.

## `prompts/final_summary.md`

**Role:** `summarisation`

Receives `report-facts.yaml` only and writes one uncited clinical report using accepted facts only.

## `prompts/final_citation_alignment.md`

**Role:** `final_citation_alignment`

Matches each final report sentence to accepted fact(s), inherits their citations, and cannot change report wording or find new evidence.

## Shared capture prompt

Case capture uses the repository-shared `prompts/workflow/capture_case.md` rather than duplicating it here.

---

# Details

## Question configuration: clinical source of truth

`questions.yaml.template` supplies the repository default, and optional local `questions.yaml` overrides it. The active file contains both:

1. the ordered reporting questions for each domain; and
2. the execution profiles that group those questions into model calls.

The number of terraces is not fixed. Custom clinical questions should be edited in local `questions.yaml` rather than hard-coded into Python. Repository default changes belong in `questions.yaml.template`.

Current domains are:

```text
diagnosis
prognosis
treatment
mrd
germline
```

Example grouping:

```yaml
execution_profiles:
  frontier:
    groups:
      diagnosis: [[DX1, DX2, DX3, DX4, DX5]]
  balanced:
    groups:
      diagnosis: [[DX1, DX2], [DX3, DX4, DX5]]
  deliberate:
    groups:
      diagnosis: [[DX1], [DX2], [DX3], [DX4], [DX5]]
```

## Conversation mechanics

The CLI owns the canonical conversation transcript; provider-side hidden chat state is not authoritative.

For split terrace groups, the effective context is reconstructed as:

```text
[case]
[permitted evidence]
[accepted upstream state]

Q/group 1
A1
Q/group 2
A2
...
```

Transcripts are persisted as `conversation-<domain>.json`. This makes runs resumable, auditable, and portable between providers.

## Model/provider configuration

`models.json.template` defines the repository-default roles, and optional local `models.json` overrides it:

```text
structure
answer
semantic_review
evidence_alignment
summarisation
final_citation_alignment
```

and the profiles:

```text
self
lmstudio
ollama
openrouter
```

Direct profiles use the same OpenAI-compatible `/chat/completions` client.

Default endpoints are:

```text
LM Studio   http://localhost:1234/v1
Ollama      http://localhost:11434/v1
OpenRouter  https://openrouter.ai/api/v1
```

Endpoint overrides are declared in the active model configuration, including:

```text
NEL_LMSTUDIO_BASE_URL
NEL_OLLAMA_BASE_URL
NEL_OPENROUTER_BASE_URL
```

Model IDs are configuration. Change them to models actually installed or available on the selected provider.

## Deny-by-default model inputs

Every model operation is packaged under:

```text
<work-dir>/state/model-steps/<sequence>-<operation>/prompt.md
```

Only the case, permitted evidence, accepted upstream state, reporting questions, conversation history, and operation-specific instructions are exposed. The model should not inspect arbitrary repository files to infer missing context.

The same bundle contract is used by `self` and direct-provider profiles.

Sequence prefixes are zero-padded (`001-`, `002-`, …), so directory-name sorting shows model operations in execution order. Resuming or retrying an operation reuses its existing directory. Each failed provider attempt preserves both `attempt-<n>.output` and `attempt-<n>.validation.txt`.

## Important artifacts

New terraced-v1 work directories keep only user-facing/root control files at the project root:

```text
<work-dir>/
├── workflow.json
├── workflow.log
├── report-final.md
├── ngs-report-debug.zip
├── ngs-report-model-steps.zip
├── input/
│   ├── case-source.md
│   ├── case.md
│   ├── case-input.json
│   ├── case-major-categories.json
│   ├── allowed-schema-diseases.json
│   ├── ngs-panel-scope.md
│   └── terraced-config.yaml
├── evidence/
│   ├── evidence-<domain>.{json,md}
│   ├── evidence-all.json
│   ├── evidence.md
│   └── card-tags.json
├── categories/
│   ├── conversation-<domain>.json
│   ├── terrace-<domain>-<n>.yaml
│   ├── answer-<domain>.yaml
│   ├── review-<domain>.json
│   ├── repair-<domain>-<n>.yaml
│   └── category-<domain>.yaml
├── synthesis/
│   ├── report-facts.yaml
│   ├── report-draft.md
│   ├── report-citation-alignment.yaml
│   └── report-cited.md
└── state/
    ├── terraced-run.json
    ├── model-usage.json
    └── model-steps/
```

Legacy flat terraced-v1 work directories remain readable/resumable; new artifacts use the nested layout unless an existing legacy artifact is being resumed.

`category-<domain>.yaml` is the accepted `fact + reason + citation` state for that domain.

## Diagnostic retrieval refresh

Each completed diagnosis terrace group may revise `provisional_cmcs`.

If a new CMC appears, the CLI expands diagnostic evidence before the next group while retaining prior Q/A turns. This supports:

- reclassification of the starting diagnosis;
- credible differentials in another disease family; and
- concurrent second pathology.

## Narrow downstream retrieval

After Step 4, `category-diagnosis.yaml` becomes the routing state for downstream evidence.

Each accepted `schema_disease` is retrieved independently. The patient-level `narrow_diagnosis` is retained as clinical context.

The key rule is: **once a narrow WHO5 diagnosis is accepted, broad starting CMCs must not drive downstream treatment/prognosis/MRD retrieval.**

## Validation and retry settings

`settings.json.template` supplies these repository defaults; optional local `settings.json` overrides them:

```json
{
  "model_profile": "openrouter",
  "terrace_profile": "balanced",
  "semantic_review_cycles": 2,
  "structural_attempts": 10,
  "token_budget": 120000
}
```

The two profile keys are added to local `settings.json` by the `provider` command;
they are not required in the shipped template.

Deterministic validators enforce JSON/YAML shape, allowed diagnosis routing values, final WHO5 diagnosis presence, exact fact/reason/citation schemas, known runtime card tags, and final citation disposition syntax. Where checks are independent, all detected defects are returned together as a numbered list. Every retry receives the complete previous output and that complete validator list; the `self` handoff prompt is regenerated with the same feedback.

A model operation is marked `validated` only after every deterministic, model-attributable consumer of that candidate has succeeded. For example, summary validation includes downstream sentence-manifest construction, while final citation-alignment validation includes deterministic cited-report assembly and report-citation validation. A failure in any such consumer remains inside the producing model operation's retry boundary, is preserved as `attempt-<n>.validation.txt`, and is returned to the model as actionable correction feedback. Only provider, filesystem, renderer, or other non-model operational failures abort outside that retry boundary.

When a summary sentence cannot be matched semantically to accepted facts, the citation aligner returns the sentence ID, exact sentence text, and reason. The complete diagnostic is supplied to the next summary synthesis cycle; it is not reduced to a generic retry instruction.

Semantic repair may reconsider clinical content. Structural repair should change only what is needed to restore the required serialization/schema.

Final synthesis is retried if a generated sentence cannot be mapped to an accepted fact.

The CLI writes concise progress to stderr. Human-facing status lines are prefixed with elapsed task time, for example `[ 0037 ] - Step 4 of 7 — review and align diagnosis evidence`. The first provider attempt is labelled `answering`; subsequent attempts are `retry 1/9`, `retry 2/9`, and so on. Low-level `[retrieve]` and `[terraced render]` diagnostics are hidden from the terminal but retained in `<work-dir>/workflow.log`. The log appends the complete terraced CLI stdout/stderr stream across invocations; orchestration protocol lines such as `HANDOFF=`, `PROMPT=` and `OUTPUT=` remain unprefixed on stdout. Direct-provider usage is accumulated in `state/model-usage.json` and summarised after Step 7. Providers that omit usage, and `self` handoffs, are reported as unavailable or partial rather than estimated.

## Empty categories and null citations

Both of these are intentionally valid:

```yaml
[]
```

and:

```yaml
citation: null
```

An empty category means there is no useful patient-level conclusion to report. A null citation means no supplied card directly matched the stated reason; it is not automatically treated as a clinical error.

## Main implementation files

| File | Purpose |
|---|---|
| `SKILL.md` | authoritative frontier/session execution procedure |
| `questions.yaml.template` | shipped reporting questions + terrace grouping defaults |
| `questions.yaml` | optional Git-ignored local question/grouping override |
| `models.json.template` | shipped model/provider/role registry defaults |
| `models.json` | optional Git-ignored local model registry override |
| `settings.json.template` | shipped retry and token-budget defaults |
| `settings.json` | optional Git-ignored local retry and token-budget override |
| `step.py` | state-machine CLI and model orchestration |
| `runtime.py` | deterministic state, validation, synthesis preparation, final rendering |
| `retrieval.py` | broad diagnosis and narrow downstream retrieval |
| `rendering.py` | evidence rendering |
| `model_registry.py` | model-role/profile resolution |
| `model_client.py` | OpenAI-compatible provider client |
| `prompts/` | workflow-local model-role prompts |
| `workflow.json` | workflow metadata and artifact allowlist |

## Current status and likely next work

`workflow.json` marks `terraced-v1` as **experimental**.

The main areas to measure before promotion are:

- reporting-question quality and ordering;
- corpus coverage under narrow diagnosis routing;
- concurrent-pathology routing;
- model quality across `frontier`, `balanced`, and `deliberate` profiles;
- whether routine semantic-review calls provide enough value for their runtime cost;
- final sentence-to-fact matching fidelity; and
- exact per-role/per-provider runtime.

The workflow is intentionally structured so these can be tuned without changing the central `fact → reason → citation → facts-only synthesis` contract.
