# terraced-v1 — Extended Guide

`terraced-v1` is an experimental NGS reporting workflow built around ordered clinical questions. It separates four jobs that are easy to conflate in a single LLM pass:

1. **clinical reasoning** — decide what is true for this patient;
2. **semantic review** — independently check those conclusions for material clinical errors;
3. **evidence attribution** — determine which retrieved evidence directly supports each accepted conclusion; and
4. **report synthesis** — turn accepted, reportable conclusions into concise prose with deterministic citation rendering.

The workflow is designed for clinical correctness, citation fidelity and auditability. The final report is intentionally downstream of the accepted clinical state rather than being the primary reasoning workspace.

> **Status:** `terraced-v1` is experimental. The repository default workflow remains separate. Select this workflow explicitly with `--terraced` or `--terraced-v1`.

---

## Contents

- [1. Current clinical questions](#1-current-clinical-questions)
- [2. Why the questions are ordered this way](#2-why-the-questions-are-ordered-this-way)
- [3. Workflow overview](#3-workflow-overview)
- [4. Role of each workflow step](#4-role-of-each-workflow-step)
- [5. Customisation](#5-customisation)
- [6. How an end-user runs terraced-v1](#6-how-an-end-user-runs-terraced-v1)
- [7. Which output files matter](#7-which-output-files-matter)
- [8. Power-user audit path](#8-power-user-audit-path)
- [9. Developer/debugging path](#9-developerdebugging-path)
- [10. Practical mental model](#10-practical-mental-model)

---

# 1. Current clinical questions

The shipped question set is defined in:

```text
workflows/terraced_v1/questions.yaml.template
```

A local `questions.yaml` overrides it when present.

The current default contains **23 ordered questions across five clinical domains**:

| Domain | Questions | Purpose |
|---|---:|---|
| Diagnosis | 6 | Establish the assigned WHO5 diagnosis, compare it with ICC, and retain WHO5 for downstream retrieval |
| Prognosis | 4 | Apply the correct disease-specific framework, then reconcile molecular modifiers |
| Treatment | 4 | Identify exact patient-specific treatment implications and modifiers |
| MRD | 4 | Separate marker suitability from actual follow-up MRD interpretation |
| Germline | 5 | Assess predisposition using molecular and clinical context without overcalling tumour-only findings |

## Diagnosis — DX1 to DX6

### DX1 — Leading diagnosis

**Question:** What is the most likely diagnosis from the supplied clinical, morphological, cytogenetic and molecular information?

**Purpose:** Establish a provisional leading diagnosis from the whole case rather than beginning gene-by-gene. The supplied clinicopathological diagnosis is a starting point, not a locked conclusion.

### DX2 — Differential diagnosis and concurrent pathology

**Question:** What plausible alternative diagnoses remain, and is there direct evidence that any finding represents a concurrent second pathology?

**Purpose:** Counter diagnostic anchoring. The workflow explicitly distinguishes a competing classification from a genuinely concurrent disease and can expand diagnostic retrieval when a credible second disease family is entertained.

### DX3 — WHO5 molecular/classification refinement

**Question:** After applying NGS, cytogenetic and other defining findings, what diagnosis is assigned under WHO 5th edition criteria, and does it change or narrow the provisional diagnosis?

**Purpose:** Apply formal disease-defining criteria only after the initial clinicopathological hypothesis and differential have been considered. WHO5 is the authoritative classifier that sets the assigned diagnostic label and accepted routing state.

### DX4 — ICC comparison

**Question:** What diagnosis would be assigned under ICC criteria, and is it materially different from the assigned WHO 5th edition diagnosis?

**Purpose:** Derive the ICC classification separately and compare it explicitly with WHO5. A materially different ICC classification may be retained as a diagnostic fact, but it does not set or replace the assigned diagnostic label or downstream routing state.

### DX5 — Exceptions, exclusions and limitations

**Question:** Do precedence rules, exclusions, informative negative findings, TP53 allelic state, assay limitations, outstanding tests or evidence for dual pathology alter the interpretation?

**Purpose:** Provide a deliberate exception-checking pass. The model must reconsider earlier conclusions rather than mechanically append caveats. Only limitations or negatives that materially alter the patient-level interpretation should survive as clinical facts.

### DX6 — Final diagnostic routing state

**Question:** What final WHO5 diagnosis or concurrent WHO5 diagnoses should control downstream retrieval, and what concise diagnostic facts should ultimately be reportable?

**Purpose:** Convert diagnostic reasoning into a stable patient-level routing state. Each accepted diagnosis has a controlled `schema_disease` for retrieval and clinically natural `narrow_diagnosis` wording.

### Diagnostic questioning pattern

```text
whole-case leading diagnosis
        ↓
credible alternatives / concurrent disease
        ↓
assigned WHO5 diagnosis
        ↓
separately derived ICC comparison
        ↓
precedence / exclusions / limitations
        ↓
final WHO5 diagnosis(es) for downstream retrieval
```

---

## Prognosis — PROG1 to PROG4

### PROG1 — Applicable prognostic framework

**Question:** Which validated disease-specific prognostic framework applies, and what patient-level risk category can actually be assigned?

**Purpose:** Establish the recognised framework before interpreting individual variants. For AML, the default guidance uses ELN 2022 as the primary framework and considers ELN 2024 Less-Intensive when clinically applicable and materially different.

### PROG2 — Molecular contribution within the framework

**Question:** Within that framework, what favourable or adverse contribution do the detected molecular findings make, including relevant TP53 allelic-state interpretation?

**Purpose:** Place detected findings into the formal disease-specific framework rather than producing disconnected gene-by-gene commentary. Findings with the same effect may be grouped.

### PROG3 — Material evidence outside the framework

**Question:** Is there important disease-specific prognostic evidence outside the formal framework, or a materially different effect in a still-relevant differential or concurrent diagnosis?

**Purpose:** Capture clinically meaningful evidence not encompassed by the formal score without pretending every detected variant must have a prognostic statement.

### PROG4 — Reportable patient-level prognosis

**Question:** After reconciling the framework, molecular modifiers, concurrent diagnoses and uncertainty, what prognostic facts are worth reporting?

**Purpose:** Convert detailed reasoning into concise patient-level conclusions and remove non-informative prose such as routine inability-to-score statements.

### Prognostic questioning pattern

```text
validated framework
      ↓
molecular modifiers within it
      ↓
material evidence outside it
      ↓
integrated reportable prognosis
```

---

## Treatment — TX1 to TX4

### TX1 — Direct treatment implication

**Question:** Which molecular or cytogenetic alteration supports a specific treatment implication for the accepted diagnosis, and in what treatment setting is that implication established, optional or investigational?

**Purpose:** Start with direct, disease-specific actionability while preserving treatment-line, approval, trial and jurisdictional qualifiers present in the evidence.

### TX2 — Exact alteration qualification

**Question:** Does the implication depend on the exact variant or alteration class, and do cytogenetic or FISH findings materially change the molecular treatment interpretation?

**Purpose:** Prevent gene-level overgeneralisation. Evidence for one alteration must not automatically be transferred to another alteration in the same gene.

### TX3 — Treatment-response modifiers

**Question:** Do any alterations materially modify response, resistance, relapse after therapy, treatment-specific survival or transplant-related management in this patient's setting?

**Purpose:** Capture treatment-specific modifiers without converting them into generic prognosis or inferring transplant indication from mutation status alone.

### TX4 — Integrated treatment reporting

**Question:** Considering all accepted concurrent diagnoses and possible management conflicts, what treatment-related molecular facts should actually be reported?

**Purpose:** Reconcile competing implications into patient-specific conclusions rather than listing independent textbook recommendations.

### Treatment questioning pattern

```text
direct actionability
      ↓
exact alteration qualification
      ↓
response / resistance / treatment modifiers
      ↓
integrated patient-specific treatment facts
```

---

## MRD — MRD1 to MRD4

### MRD1 — Validated marker suitability

**Question:** Which detected alterations are validated molecular MRD markers for the accepted diagnosis, and what disease-specific baseline and subsequent monitoring approach is supported?

**Purpose:** Establish what can appropriately be followed before interpreting a current MRD result. A diagnostic specimen may support a prospective marker recommendation even when no follow-up MRD result exists.

### MRD2 — Preferred versus complementary markers

**Question:** If several alterations could be followed, which should be preferred and which are only complementary?

**Purpose:** Prioritise the most disease-specific and validated marker rather than allowing a less-specific clonal mutation to displace a superior disease marker.

### MRD3 — Follow-up interpretation

**Question:** If this is a follow-up specimen, what can detected or non-detected findings mean at this treatment timepoint given assay sensitivity, quantitative level and serial kinetics?

**Purpose:** Separate **marker suitability** from **current MRD status**. Routine panel negativity must not be equated with biological absence or molecular remission.

### MRD4 — Reportable MRD conclusion

**Question:** After integrating marker suitability and specimen context, what MRD facts or recommendations are worth reporting?

**Purpose:** Preserve positive marker/baseline recommendations when appropriate while avoiding generic negative prose when no useful molecular MRD implication exists.

### MRD questioning pattern

```text
what can be followed?
      ↓
what should be preferred?
      ↓
what does this follow-up result mean?
      ↓
what MRD fact/recommendation is worth reporting?
```

---

## Germline — GL1 to GL5

### GL1 — Molecular suspicion

**Question:** Do any detected variants raise a credible possibility of germline predisposition when gene, exact variant class, VAF and known prevalence are considered together?

**Purpose:** Screen for legitimate germline concern without using VAF alone or diagnosing germline status from tumour-only sequencing.

### GL2 — Clinical phenotype and family history

**Question:** Do family history, age, phenotype, morphology or other clinical features strengthen or weaken suspicion of a relevant germline syndrome?

**Purpose:** Integrate the molecular result with the patient's clinical context rather than treating predisposition as a sequence-only question.

### GL3 — What molecular architecture can establish

**Question:** Does the molecular architecture support or weaken germline predisposition, and what phase, constitutional-allele or clonal relationships can actually be established?

**Purpose:** Explicitly prevent inference of cis/trans phase, constitutional allele identity or clonal co-occurrence from bulk VAF alone.

### GL4 — Clinical consequence of uncertainty

**Question:** Would uncertainty about germline versus somatic origin materially change diagnosis, prognostic-framework application, treatment interpretation, donor selection or another patient-level conclusion?

**Purpose:** Prioritise germline uncertainty when it changes clinical interpretation or management rather than reporting every theoretical concern.

### GL5 — Report and confirmation

**Question:** What germline-predisposition facts, if any, should be reported, and what constitutional confirmation wording is justified?

**Purpose:** Convert justified suspicion into appropriately cautious report language. If no germline concern is supported, the expected result is an empty fact list rather than a negative paragraph.

### Germline questioning pattern

```text
molecular suspicion
      ↓
clinical / family-history support
      ↓
what the molecular architecture can actually establish
      ↓
clinical consequences of uncertainty
      ↓
reportable suspicion + confirmation recommendation
```

---

# 2. Why the questions are ordered this way

The question design is intentionally asymmetric. Diagnosis receives six questions because it establishes the routing state for every later domain and separately compares the assigned WHO5 diagnosis with ICC. Prognosis, treatment and MRD each receive four questions because they operate after diagnosis has been accepted. Germline receives five because constitutional origin can affect diagnosis, prognosis, treatment and donor selection and therefore needs both molecular and clinical qualification.

The main design principles are below.

## 2.1 Whole-case reasoning before gene-by-gene interpretation

The first diagnostic question asks for the most likely diagnosis from the complete case. This prevents the workflow from starting with a mutation and reasoning outward from the gene alone.

The intended direction is:

```text
patient phenotype + morphology + cytogenetics + molecular findings
                              ↓
                     clinicopathological diagnosis
                              ↓
                   disease-specific gene meaning
```

rather than:

```text
gene detected → search all gene associations → construct diagnosis around them
```

## 2.2 Differential diagnosis before formal classification

DX2 deliberately asks about competing and concurrent pathology before DX3 applies the formal WHO5 disease-defining rules. DX4 then derives the ICC diagnosis separately and asks whether it is materially different, without allowing ICC to replace the assigned WHO5 label.

This reduces the risk that a strong molecular classifier prematurely suppresses consideration of a second genuine disease process.

## 2.3 Final diagnosis before downstream evidence retrieval

Prognosis, treatment and MRD evidence are disease-dependent. `terraced-v1` therefore does not simply retrieve every gene-associated card at the beginning and ask the model to sort it out.

Instead:

```text
broad diagnostic retrieval
        ↓
diagnostic reasoning
        ↓
accepted WHO5 diagnosis(es)
        ↓
narrow disease-specific downstream retrieval
```

If there are genuinely concurrent diseases, evidence is retrieved against each accepted diagnosis independently.

## 2.4 Framework before molecular modifiers

Prognosis begins by deciding which validated disease-specific framework applies. Molecular findings are interpreted within that framework only afterward.

This makes the framework the organising structure rather than generating a catalogue of gene associations and trying to infer the overall risk afterward.

## 2.5 Direct actionability before treatment modifiers

Treatment first asks whether there is a specific actionable alteration, then checks exact alteration class and only then considers response/resistance/transplant-related modifiers.

This keeps direct therapeutic implications separate from weaker treatment-associated evidence.

## 2.6 Marker suitability before MRD status

MRD deliberately asks two different questions:

1. **Is this alteration a suitable MRD marker?**
2. **What does the current follow-up result mean?**

A diagnostic sample can support a future MRD-marker recommendation without supporting a current MRD-status statement.

## 2.7 Germline suspicion is progressively constrained

Germline reasoning starts with molecular suspicion, then incorporates phenotype/family history, then asks what can actually be inferred from the sequencing architecture, then asks whether the uncertainty is clinically consequential.

This deliberately avoids simplistic rules such as “VAF near 50% = germline”.

## 2.8 Each domain ends with a reportability question

The final question in every domain asks, in effect:

> After all of that reasoning, what is actually worth saying about this patient?

This is important because information needed to reason correctly is not necessarily information that belongs in a clinical report.

---

# 3. Workflow overview

```mermaid
flowchart TD
    A[Patient case] --> B[Step 1A: Capture case]
    B --> C[Step 1B: Structure case<br/>provisional CMCs + genes + preserved facts]
    C --> D[Step 2: Broad diagnostic retrieval]
    D --> E[Step 3: Diagnosis questions<br/>DX1 → DX2 → DX3 → DX4 → DX5 → DX6]

    E --> F{New credible disease family?}
    F -- Yes --> G[Expand diagnostic evidence]
    G --> E
    F -- No --> H[Step 4: Independent diagnosis review]

    H --> I{Material diagnostic defect?}
    I -- Yes --> E
    I -- No --> J[Evidence alignment]
    J --> K[Accepted WHO5 diagnosis(es)]

    K --> L[Step 5: Prognosis]
    L --> M[Treatment]
    M --> N[MRD]
    N --> O[Germline]

    L -. each domain .-> P[Terraced answers → semantic review/repair → evidence alignment]
    M -. each domain .-> P
    N -. each domain .-> P
    O -. each domain .-> P

    P --> Q[Accepted fact + reason + citation state]
    Q --> R[Step 6A: Target-activation extraction]
    R --> S[Diagnosis-card activation draw]
    S --> T[Deterministic activated targets]
    T --> U[Four-field fact classification]
    U --> V[Deterministic reportability gates]
    V --> W[Lossless retained-facts synthesis]
    W --> X[Bidirectional sentence-to-fact alignment]
    X --> Y[Deterministic citation render]
    Y --> Z[report-final.md]
    Z --> AA[Step 7: Package / deliver]
```

The central separation is:

```text
CLINICAL REASONING             EVIDENCE ATTRIBUTION             REPORTING
------------------             --------------------             ---------
fact + reason          →       add citation only        →       select reportable facts
                                                                  ↓
                                                               write prose
                                                                  ↓
                                                        sentence ↔ fact alignment
                                                                  ↓
                                                        inherit accepted citations
                                                                  ↓
                                                        deterministic rendering
```

The report-writing stage is not allowed to become a second clinical reasoning engine.

---

# 4. Role of each workflow step

The canonical workflow is:

```text
1a  capture case
1b  structure case
2   retrieve broad diagnostic evidence
3   terraced diagnosis
4   diagnosis review + evidence alignment
5   downstream terraced categories
6   target activation + deterministic reportability + lossless synthesis + citation alignment + render
7   package/deliver
```

## Step 0 — Setup

**Role:** Initialise the run and choose execution configuration.

The setup stage establishes:

- operating mode;
- model profile;
- terrace grouping profile;
- work directory;
- case source and workflow assets.

The same clinical workflow can therefore run through the current frontier/session model or directly through configured OpenAI-compatible providers.

## Step 1A — Capture case

**Role:** Preserve the supplied case faithfully.

This stage captures the original clinical and laboratory information before molecular interpretation is allowed to reshape it.

## Step 1B — Structure case

**Role:** Convert the captured case into a canonical machine-usable patient state.

`input/case-input.json` includes:

- provisional case-major categories (`provisional_cmcs`);
- supplied disease wording;
- detected genes;
- preserved patient-level facts; and
- a mandatory source-faithful `detected_variants_summary`.

The provisional CMC is a retrieval scaffold, not the final diagnosis.

The detected-variant summary is later prepended deterministically to the final report so the basic patient NGS result cannot be accidentally omitted or paraphrased by report synthesis.

## Step 2 — Broad diagnostic retrieval

**Role:** Retrieve enough evidence to challenge the starting diagnosis.

Retrieval uses provisional CMCs and detected genes and includes relevant diagnosis cards plus gene-matched germline/predisposition evidence.

The initial evidence set is deliberately broader than downstream prognosis/treatment/MRD retrieval because the diagnosis is not yet settled.

## Step 3 — Diagnosis questioning

**Role:** Establish the final WHO5 diagnostic state.

The model works through DX1–DX6 in the grouping defined by the active terrace profile.

Later questions may:

- add a conclusion;
- remove an earlier conclusion;
- qualify it;
- replace it; or
- introduce a credible new provisional CMC.

If a new disease family emerges, the CLI expands diagnostic retrieval before the next question group.

The final accepted state may contain one or more WHO5 diagnoses. The assigned label and both diagnosis fields are derived from WHO5; ICC is comparison-only. `schema_disease` is the controlled downstream retrieval key; `narrow_diagnosis` is the patient-level WHO5 wording.

## Step 4 — Diagnosis review and evidence alignment

**Role:** Independently check diagnosis, repair material errors, then attach supporting evidence.

A fresh semantic reviewer should fail the diagnosis only for material defects such as:

- contradiction with the case;
- contradiction between accepted facts;
- wrong disease/framework application;
- a materially unmet premise;
- incorrect WHO5 routing; or
- material evidence misinterpretation.

If review fails, the owning terraced conversation resumes and returns a complete replacement diagnostic state.

After semantic acceptance, evidence alignment preserves each accepted `fact` and `reason` and adds only `citation`.

A citation may legitimately be `null` when no supplied card directly supports the reason.

## Step 5 — Downstream clinical domains

**Role:** Process prognosis, treatment, MRD and germline after diagnosis is stable.

The order is:

```text
prognosis → treatment → MRD → germline
```

Each domain receives:

- the structured patient case;
- accepted upstream clinical state;
- assay-scope constraints;
- its ordered clinical questions; and
- evidence retrieved using the accepted WHO5 diagnosis or diagnoses.

Each domain follows the same general pattern:

```text
narrow disease-specific retrieval
              ↓
ordered clinical questions
              ↓
semantic review
        ↙ fail     pass ↘
     repair       evidence alignment
                         ↓
                 accepted category state
```

The accepted `category-*.yaml` files are the complete clinical source of truth for their domains.

## Step 6 — Report synthesis and deterministic rendering

**Role:** Select reportable molecular content deterministically, then compress it into prose without reopening clinical reasoning.

Step 6 deliberately separates context extraction, fact description, policy, prose generation and provenance. No model directly decides whether a fact is reported.

### 6A. Target-activation context

A constrained model pass reads the clinical stem, structured case and accepted diagnosis state. It extracts only:

- molecular targets explicitly mentioned in the stem;
- targets previously detected;
- targets explicitly requested or excluded; and
- diagnoses explicitly raised in the stem.

The accepted diagnosis state is added deterministically. The pass does not infer phenotype-to-gene relationships and does not see reportability outcomes. Its output is `synthesis/activation-context.yaml`.

### 6B. Diagnosis-card activation

The CLI performs one batched, diagnosis-focused draw using the diagnoses raised by the stem or accepted diagnosis state. In the current implementation, exact-disease `diagnosis` cards with evidence tier `guideline criterion` are eligible activation evidence. The draw is persisted as `evidence/evidence-reportability-activation.json`.

Code derives diagnosis targets alteration-aware rather than blindly unioning card gene tags. Targets explicitly named in an accepted narrow diagnosis are eligible; disease-wide targets are eligible only when the molecular criterion cards share a common target component. Fusion/rearrangement cards activate the fusion target rather than each component gene independently. This prevents broad diagnoses such as AML, or an NPM1::RARA criterion card, from spuriously activating unrelated gene-level negatives. The resulting targets are unioned with direct case targets and written to `synthesis/activated-targets.yaml` with basis and provenance. The final activated-target list is therefore code-derived rather than model-authored.

### 6C. Four-field fact classification and deterministic reportability

A separate constrained model pass classifies every accepted fact exactly once using only four observations:

```text
molecular
targets
polarity: detected | not_detected | not_a_result
negative_consequence
```

The model cannot emit `report`, `omit`, `routine_negative` or an equivalent disposition. A deterministic validator requires exact manifest coverage, stable fact order, valid target syntax and a closed polarity vocabulary. The observations are persisted in `synthesis/reportability-classification.yaml`.

Code then applies stable reportability rules and records every decision in `synthesis/reportability-decisions.yaml`. Important rules include:

- non-molecular fact → quarantine;
- absent molecular target + activated target → retain;
- absent molecular target + no activation → quarantine;
- mixed activated/unactivated absent targets in one inseparable fact → retain conservatively;
- negative consequence → retain only when that domain's reporting-question policy explicitly permits it;
- direct positive result already represented by the deterministic detected-variant summary → quarantine as duplicate;
- direct positive result not represented by that summary → retain; and
- other molecular interpretation → retain.

`synthesis/reportability-review.yaml` remains the compact compatibility contract containing `quarantine_fact_ids`. `synthesis/report-facts-quarantined.yaml` preserves each removed fact together with its four observations, target-activation evidence, deterministic rule ID and generated rationale.

### 6D. Lossless retained-facts synthesis

The summariser receives `synthesis/report-facts.yaml` only. Its task is lossless semantic compression:

- merge genuinely overlapping facts;
- remove literal repetition;
- shorten wording; and
- improve flow.

It may not discard a distinct retained fact, introduce a new clinical conclusion, alter a qualification or choose which retained facts are important. There is no model-driven negative-safety rescue.

### 6E. Bidirectional sentence-to-fact alignment

Each final report sentence is mapped back to one or more retained accepted fact IDs. The alignment model cannot rewrite the prose or search for new evidence. Deterministic validation checks both directions:

- every report sentence must map to eligible retained fact(s); and
- every retained fact must be covered by at least one report sentence.

If a sentence is unsupported or a retained fact was omitted, synthesis is retried with exact deterministic feedback. Multiple retained facts may map to one compressed sentence.

The provenance chain is:

```text
CARD
  ↓ supports
REASON
  ↓ justifies
FACT
  ↓ maps to
REPORT SENTENCE
  ↓ inherits
CITATION
```

### 6F. Deterministic citation render

Code then validates runtime card tags, inherits citations from mapped accepted facts, deduplicates publications, assigns Vancouver numbers and renders the final report. The source-faithful detected-variant summary from `case-input.json` is prepended deterministically.

# 5. Customisation

`terraced-v1` deliberately separates clinical workflow logic from local model/provider configuration.

## 5.1 Local configuration files

The repository ships templates:

| Repository default | Optional local override | Controls |
|---|---|---|
| `models.json.template` | `models.json` | providers, model IDs and model role bindings |
| `questions.yaml.template` | `questions.yaml` | clinical questions and terrace grouping |
| `settings.json.template` | `settings.json` | retry/review/token settings and saved local defaults |

A local override is used when present; otherwise the template is read directly.

To customise only what you need:

```bash
cp workflows/terraced_v1/models.json.template workflows/terraced_v1/models.json
cp workflows/terraced_v1/questions.yaml.template workflows/terraced_v1/questions.yaml
cp workflows/terraced_v1/settings.json.template workflows/terraced_v1/settings.json
```

These local working files are Git-ignored. Edit the corresponding `.template` file when proposing a new repository default.

## 5.2 Clinical-question customisation

Within `questions.yaml`, the workflow can change:

- question wording;
- question guidance;
- question count;
- question order; and
- grouping of consecutive questions into model calls.

The number of questions is deliberately not hard-coded as a fixed terrace count.

## 5.3 Terrace grouping profiles

The default question template defines three execution profiles:

| Profile | Grouping | Intended use |
|---|---|---|
| `frontier` | One model call per clinical domain | Strong frontier/session models; lowest call count |
| `balanced` | Approximately two calls per domain | Capable local models with moderate context/reasoning ability |
| `deliberate` | One call per individual question | Weaker local models, debugging and evaluation |

These profiles **do not change the clinical questions or their order**. They change only how many consecutive questions the model is asked to handle in a call.

Current default grouping:

```text
frontier
  diagnosis:  DX1-DX6 in one call
  prognosis:  PROG1-PROG4 in one call
  treatment:  TX1-TX4 in one call
  MRD:        MRD1-MRD4 in one call
  germline:   GL1-GL5 in one call

balanced
  diagnosis:  DX1-DX2 | DX3-DX6
  prognosis:  PROG1-PROG2 | PROG3-PROG4
  treatment:  TX1-TX2 | TX3-TX4
  MRD:        MRD1-MRD2 | MRD3-MRD4
  germline:   GL1-GL2 | GL3-GL5

deliberate
  one call per individual question
```

## 5.4 Model/provider customisation

The supplied profiles are:

```text
self
lmstudio
ollama
openrouter
```

The model configuration separates workflow roles:

```text
structure
answer
semantic_review
evidence_alignment
target_activation
reportability
summarisation
final_citation_alignment
```

A power user can therefore assign different models to different jobs without changing the clinical workflow. For example, a stronger model can perform `answer` while another configured model handles constrained alignment or review tasks.

The default repository templates currently bind all roles in a profile to the same model, but the role separation is already available for custom configurations.

## 5.5 Runtime settings

`settings.json.template` currently exposes:

```text
semantic_review_cycles
structural_attempts
token_budget
```

Provider/terrace defaults may also be stored locally using the `provider` command.

## 5.6 Per-run overrides

A setup command may override saved defaults for a single run:

```text
--model-profile ...
--terrace-profile ...
```

This is useful for comparing models or terrace grouping strategies without editing configuration files.

---

# 6. How an end-user runs terraced-v1

## 6.1 Frontier / ChatGPT skill harness

From the end-user perspective, the workflow selector is the main interface.

```text
ngs-report --terraced
```

or explicitly:

```text
ngs-report --terraced-v1
```

The same selector is available in the supported demonstration and validation modes:

```text
nel-demo example 1 --terraced
nel-validate 1C --terraced
nel-validate-function 3B --terraced
nel-validate-brief 8 --terraced
```

The normal skill user does **not** need to manually run Steps 1–7 or inspect the intermediate files.

The root `SKILL.md` routes the request to `workflows/terraced_v1/SKILL.md`, and the CLI is the authoritative workflow orchestrator.

Default frontier settings are:

```text
model profile:   self
terrace profile: frontier
```

## 6.2 Direct/local-model execution

Create the repository Python environment once:

```bash
python3 -m venv .env
.env/bin/python -m pip install -r requirements.txt
```

Set a local provider and terrace profile, for example:

```bash
.env/bin/python workflows/terraced_v1/step.py provider lmstudio balanced
```

Then initialise and run a case:

```bash
.env/bin/python workflows/terraced_v1/step.py setup \
  --mode ngs-report \
  --project \
  --case-file case.md

.env/bin/python workflows/terraced_v1/step.py --all
```

For OpenRouter, configure the API key first:

```bash
export OPENROUTER_API_KEY='...'
```

A specific run can override the saved model and terrace profiles during setup.

## 6.3 Manual step execution

Manual execution is primarily useful for power users and developers:

```bash
.env/bin/python workflows/terraced_v1/step.py 3 --work-dir <work-dir>
```

The full workflow remains Steps `1a`, `1b`, `2`, `3`, `4`, `5`, `6`, and `7`.

---

# 7. Which output files matter

Different users should pay attention to different layers of the work directory.

## 7.1 Normal clinical/end-user

### `report-final.md` — read this

This is the final rendered clinical report.

For most end-users, this is the only file that needs routine review.

### `ngs-report-debug.zip` — retain this

This is the portable troubleshooting/audit package produced by delivery.

A normal user generally does not need to inspect it unless:

- a conclusion appears wrong;
- a report needs audit;
- the run needs to be shared for troubleshooting; or
- a developer asks for the supporting workflow artifacts.

### Recommended normal-user mental model

```text
report-final.md        ← clinical output to read
ngs-report-debug.zip   ← retain for audit/support
```

---

# 8. Power-user audit path

A power user is usually interested in **why** the final report said something, or why something was omitted.

The most useful files are below.

## 8.1 `categories/category-diagnosis.yaml`

This is the accepted diagnostic clinical state after semantic review and evidence alignment.

It contains the final WHO5 routing diagnosis or diagnoses and the accepted diagnostic facts, reasons and citations.

This is the first file to inspect when questioning the final diagnosis.

## 8.2 `categories/category-prognosis.yaml`

Accepted prognostic clinical conclusions after review and evidence alignment.

## 8.3 `categories/category-treatment.yaml`

Accepted treatment-related clinical conclusions after review and evidence alignment.

## 8.4 `categories/category-mrd.yaml`

Accepted MRD marker/status conclusions and recommendations after review and evidence alignment.

## 8.5 `categories/category-germline.yaml`

Accepted germline-predisposition conclusions and confirmation recommendations after review and evidence alignment.

### Why the `category-*.yaml` files matter

These files are the **complete accepted clinical source of truth** for their domains.

A useful audit question is:

> Was the questionable statement already present in the accepted clinical reasoning, or did the problem arise later during report synthesis?

If the clinical conclusion is already wrong in `category-*.yaml`, investigate the relevant terrace/review/retrieval chain. If it is correct there but wrong in `report-final.md`, investigate synthesis or citation alignment instead.

## 8.6 `evidence/evidence-<domain>.md`

Human-readable evidence made available to that clinical domain.

Use this to ask:

> What evidence did the clinical reasoning actually have available?

Examples:

```text
evidence/evidence-diagnosis.md
evidence/evidence-prognosis.md
evidence/evidence-treatment.md
evidence/evidence-mrd.md
evidence/evidence-germline.md
```

## 8.7 `synthesis/activation-context.yaml`

The model-extracted direct activation signals from the clinical stem plus explicitly raised stem diagnoses. It records why each direct target entered consideration but does not decide reportability.

## 8.8 `evidence/evidence-reportability-activation.json`

The diagnosis-focused activation card draw. Use this to audit which curated diagnosis cards contributed molecular targets to activation.

## 8.9 `synthesis/activated-targets.yaml`

The deterministic union of direct case activation and alteration-aware diagnosis-card-derived targets, including activation bases and provenance. This is the authoritative activated-target list used by the reportability gates.

## 8.10 `synthesis/reportability-classification.yaml`

The model-authored exhaustive four-field observations for every accepted fact: `molecular`, `targets`, `polarity`, and `negative_consequence`. The model does not supply the final disposition.

## 8.11 `synthesis/reportability-decisions.yaml`

The code-derived decision for every accepted fact, including `retain`/`quarantine`, a stable rule ID, generated rationale and per-target activation status. This is the primary audit file for why a fact survived or was removed.

## 8.12 `synthesis/reportability-review.yaml`

The compact compatibility contract containing the deterministically derived `quarantine_fact_ids` in accepted-manifest order.

## 8.13 `synthesis/report-facts.yaml`

The retained accepted fact text handed to lossless report synthesis.

## 8.14 `synthesis/report-facts-quarantined.yaml`

Accepted facts removed from ordinary synthesis. Each row preserves its original fact/reason/citation plus the four-field classification, activation evidence and deterministic decision/rationale. This is the fastest single file for answering why a particular accepted fact was omitted.

## 8.15 `synthesis/report-draft.md`

The uncited losslessly compressed report text. There is no pre-rescue draft and no negative-safety-review artifact.

## 8.16 `synthesis/report-citation-alignment.yaml`

The semantic mapping from final report sentence IDs back to retained fact IDs. Deterministic validation requires every sentence to be supported and every retained fact to be covered.

## 8.17 `synthesis/report-cited.md`

The immediate cited representation before final Vancouver rendering.

## 8.18 `report-final.md`

The user-facing molecular NGS report after deterministic citation rendering and prepending of the source-faithful detected-variant summary.


# 9. Developer/debugging path

Developers usually need to determine **where an error first appeared** and whether it came from retrieval, model reasoning, validation/repair, synthesis, or deterministic orchestration.

## 9.1 `workflow.log`

The complete CLI log for the run.

This should generally be the first operational debugging file inspected. It preserves workflow messages even when routine retrieval/render messages are masked from the normal terminal display.

## 9.2 `state/model-steps/`

Chronological packaged model operations.

Each operation is stored under a zero-padded sequence directory so model calls retain execution order.

These bundles expose the exact inputs presented to a model operation and its output. Failed direct-provider attempts may also preserve attempt outputs and validation diagnostics.

Use this directory for:

- prompt debugging;
- structural-validation failures;
- semantic-review loops;
- malformed model output;
- comparing model behaviour between profiles; and
- identifying the first model step at which a clinical conclusion changed incorrectly.

## 9.3 `ngs-report-model-steps.zip`

Portable package of model-step bundles when model bundles exist.

Useful for sharing or comparing runs without navigating the live work directory.

## 9.4 `state/terraced-run.json`

The workflow state/checkpoint record.

Use it for orchestration, resume and state-transition debugging.

## 9.5 `state/model-usage.json`

Provider-reported model usage when available.

Useful for runtime/token optimisation and comparing model/terrace configurations.

## 9.6 `categories/conversation-<domain>.json`

The reconstructed canonical terraced conversation for a domain.

These files are especially useful for evaluating whether later questions actually reconsidered earlier conclusions.

Examples:

```text
categories/conversation-diagnosis.json
categories/conversation-prognosis.json
categories/conversation-treatment.json
categories/conversation-mrd.json
categories/conversation-germline.json
```

## 9.7 `categories/answer-<domain>.yaml`

The completed clinical answer state before final category evidence alignment.

Useful for separating clinical reasoning from citation-attribution behaviour.

## 9.8 `categories/review-<domain>.json`

The independent semantic review result for the domain.

Inspect this when asking:

- Did the reviewer detect the error?
- Was a failure appropriately high-threshold?
- Did it explain the material defect clearly enough for repair?

## 9.9 `categories/terrace-<domain>-<n>.yaml`

Intermediate state produced by individual question groups.

Most useful with `balanced` or `deliberate` execution, where the progression between question groups is visible.

## 9.10 `categories/repair-<domain>-<n>.yaml`

Replacement state generated after a semantic-review failure.

Use this to evaluate whether repair fixed the stated defect without creating regressions elsewhere in the clinical state.

## 9.11 `input/case-input.json`

The canonical structured patient state.

If every downstream stage appears wrong, verify this early. A case-structuring error can contaminate the entire workflow.

## 9.12 `evidence/evidence-*.json`

Machine-readable evidence used by retrieval and later model packaging.

Use these instead of the Markdown evidence views when debugging:

- retrieval logic;
- disease routing;
- card inclusion/exclusion;
- duplicate evidence behaviour; or
- runtime card tags.

## 9.13 `evidence/evidence-all.json`, `evidence/evidence.md`, `evidence/card-tags.json`

Aggregated final evidence/citation assets used during synthesis and deterministic rendering.

Use these when debugging publication deduplication, runtime card tags or final reference construction.

### Recommended developer debugging order

```text
OPERATIONAL FAILURE
workflow.log
    ↓
state/terraced-run.json
    ↓
state/model-steps/<relevant operation>/

CLINICAL ERROR
input/case-input.json
    ↓
evidence/evidence-<domain>.json
    ↓
categories/conversation-<domain>.json
    ↓
categories/answer-<domain>.yaml
    ↓
categories/review-<domain>.json
    ↓
categories/category-<domain>.yaml

FINAL REPORT / CITATION ERROR
categories/category-*.yaml
    ↓
synthesis/reportability-classification.yaml
    ↓
synthesis/reportability-review.yaml
    ↓
synthesis/report-facts*.yaml
    ↓
synthesis/report-draft.md
    ↓
synthesis/report-citation-alignment.yaml
    ↓
synthesis/report-cited.md
    ↓
report-final.md
```

---

# 10. Practical mental model

The workflow has three useful levels of truth:

```text
PATIENT / EVIDENCE STATE
        ↓
ACCEPTED CLINICAL STATE
categories/category-*.yaml
        ↓
REPORTABLE FACT SET
synthesis/report-facts.yaml
        ↓
PATIENT-FACING REPRESENTATION
report-final.md
```

For different users:

```text
NORMAL USER
│
├── report-final.md                  ← read this
└── ngs-report-debug.zip             ← retain for audit/support

POWER USER / CLINICAL AUDIT
│
├── categories/category-*.yaml       ← accepted clinical conclusions
├── evidence/evidence-*.md           ← evidence available to each domain
├── synthesis/activation-context.yaml
├── evidence/evidence-reportability-activation.json
├── synthesis/activated-targets.yaml
├── synthesis/reportability-classification.yaml
├── synthesis/reportability-decisions.yaml
├── synthesis/reportability-review.yaml
├── synthesis/report-facts.yaml      ← retained for synthesis
├── synthesis/report-facts-quarantined.yaml
├── synthesis/report-draft.md
└── synthesis/report-citation-alignment.yaml

DEVELOPER
│
├── workflow.log                     ← operational history
├── state/model-steps/               ← exact model operations/retries
├── ngs-report-model-steps.zip
├── state/terraced-run.json
├── state/model-usage.json
├── input/case-input.json
├── evidence/evidence-*.json
├── categories/conversation-*.json
├── categories/answer-*.yaml
├── categories/review-*.json
├── categories/terrace-*.yaml
└── categories/repair-*.yaml
```

The most important architectural distinction is:

> **`categories/category-*.yaml` is the accepted clinical source of truth; `report-final.md` is its patient-facing representation.**

That distinction makes the workflow auditable. A power user can inspect the accepted clinical conclusions without having to reverse-engineer them from polished report prose, while a normal end-user can remain focused on the final report.
