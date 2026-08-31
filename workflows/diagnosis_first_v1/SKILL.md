---
name: ngs-evidence-layer-diagnosis-first-v1
description: Diagnosis-first workflow for ngs-report, nel-demo, nel-validate, nel-validate-function, and nel-validate-brief.
---
# NGS evidence layer — diagnosis-first-v1

## Scope

Supported modes only:

- `ngs-report`
- `nel-demo example <N>`
- `nel-validate <case-id>`
- `nel-validate-function <case-id>`
- `nel-validate-brief <case-id>`

This workflow implements the diagnosis-first pipeline. Environment setup is owned by Step 0 below; after Step 0 defines `<python>`, use it for every deterministic command in this workflow.

The workflow is:

0. setup;
1. capture/structure case and assign Step-1 case major category (CMC1);
2. retrieve broad diagnosis + gene-matched germline evidence and deterministically generate the R0-R1 YAML draft template;
3. model-complete R0-R1 in `report-draft-dx.yaml` and set one refined CMC (CMC2);
4. generate the branch-specific rule view, retrieve/render downstream evidence, and deterministically generate the matching remainder YAML draft template;
5. model-complete the remainder, or all R0-R5 again when CMC changed;
6. deterministically assemble `report-draft.yaml` with all `omit: true` rules removed, model-complete the section-oriented `report-summary.yaml`, then deterministically render citations and final Markdown;
7. use the existing delivery/validation behaviour and packager command.

`downstream_filter_disease` is not used in this diagnosis-first workflow. CMC2 is the downstream disease-routing value.

## Global access/model rules

File access is deny-by-default. In each model step read only the files explicitly declared below. Deterministic commands may read their required inputs but do not make those inputs model-readable. Do not inspect deterministic Python source while running the workflow. Use a fresh bounded model session for each model step and do not carry information between model steps unless an allowed input supplies it.

Shared patient-result semantics from the original workflow apply to Steps 1B, 3 and 5: treat explicitly complete tests as complete within their stated scope; do not assume unmentioned tests; if cytogenetics are absent, normal conventional cytogenetics may be used only as a workflow assumption and must not be stated as a performed negative test.

For Steps 3 and 5, `<work-dir>/ngs-panel-scope.md` is the complete assay-scope boundary for gene-level NGS negative inference. When the patient NGS result is complete, a gene listed in that file but absent from the detected-variant list is negative only for the variant classes stated in the panel-scope file. Use that negative result to resolve reporting-rule criteria and exclusions; do not treat the gene as unresolved merely because it is not individually listed. Do not call this whole-gene biological wild type or extend the inference to unlisted variant classes.

For diagnosis-first rule drafting, the workflow-local reporting policy's REPORT/OMIT taxonomy is encoded in YAML as follows:

- REPORT -> `omit: false` or `omit: No`;
- OMIT -> `omit: true` or `omit: Yes`.

Every rule must still contain at least one atomic statement. Omission controls downstream inclusion only.

## Step 0 — Setup

Select the explicit mode before reading case-specific inputs.

At Step 0 only, prepare the repository-local Python environment before running the workflow setup command:

```bash
python3 -m venv .env
.env/bin/python -m pip install -r requirements.txt
```

Set `<python>` to `.env/bin/python` for all diagnosis-first deterministic commands. The requirements install must succeed; it supplies `PyYAML>=6.0`, which is required by the diagnosis-first YAML draft/report tooling. Do not run this environment bootstrap from the root router or from `legacy-v1`.

Choose the setup work-directory argument exactly once:

- supplied directory: `<setup-work-arg>` is `--work-dir <supplied-directory>`;
- exact `->project` modifier: `<setup-work-arg>` is `--project`;
- otherwise: `<setup-work-arg>` is empty.

Run exactly one diagnosis-first setup command for the selected mode:

```bash
# ngs-report
<python> scripts/setup_workflow.py --workflow diagnosis-first-v1 --mode ngs-report <setup-work-arg>

# nel-demo example <N>
<python> scripts/setup_workflow.py --workflow diagnosis-first-v1 --mode nel-demo --example <N> <setup-work-arg>

# nel-validate <case-id>
<python> scripts/setup_workflow.py --workflow diagnosis-first-v1 --mode nel-validate --case-id <case-id> <setup-work-arg>

# nel-validate-function <case-id>
<python> scripts/setup_workflow.py --workflow diagnosis-first-v1 --mode nel-validate-function --case-id <case-id> <setup-work-arg>

# nel-validate-brief <case-id>
<python> scripts/setup_workflow.py --workflow diagnosis-first-v1 --mode nel-validate-brief --case-id <case-id> <setup-work-arg>
```

Record output line 1 as `<work-dir>` and print `Working directory: <absolute-path>`.

For `nel-demo`, record the supplied example number as `<demo-example>`. Setup has already written the selected clinical text to `<work-dir>/case.md`; no expected/marking file exists yet.

For `nel-validate <case-id>`, `nel-validate-function <case-id>`, or `nel-validate-brief <case-id>`, record `<validation-case>` as the supplied case ID. Setup deterministically writes `<work-dir>/case.md`; do not read validation marking files. For `nel-validate-function`, bundled marking criteria and `validation/case_functional_manifest.md` remain forbidden model inputs.

Setup also generates the branch-independent procedural assets used later:

- `<work-dir>/case-major-categories.json`;
- `<work-dir>/ngs-panel-scope.md`, copied from the canonical bundled assay definition;
- `<work-dir>/reporting-rules-dx.md` containing only the prompt-owned R0-R1 diagnosis rule view.

Setup is additive for an existing directory. It may replace these procedural assets, but it must not overwrite an existing `case.md` with different validation-case content or modify any later workflow draft.

For all supported modes record `<format-prompt>` as `workflows/diagnosis_first_v1/prompts/formatting/default.md`. Record the path only and do not read it until Step 6B.

## Step 1 — Case capture and CMC1

### Step 1A

For `nel-validate`, `nel-validate-function`, and `nel-validate-brief`, Step 0 has already written `<work-dir>/case.md` deterministically. Do not run a second case-retrieval command. Do not model-read bundled validation sources, `validation/case_functional_manifest.md`, or marking criteria.

For other modes, use a fresh model session and read only `prompts/workflow/capture_case.md` plus the designated case source (`<work-dir>/case.md` for demo). Write only `<work-dir>/case.md`.

### Step 1B

Use the `<work-dir>/case-major-categories.json` generated in Step 0. Do not regenerate it. Then use a fresh model session. Read only:

- `prompts/workflow/structure_case.md`;
- `<work-dir>/case.md`;
- `<work-dir>/case-major-categories.json`.

The model writes only `<work-dir>/case-input.json`. Its `case_major_category` is CMC1.

## Step 2 — Diagnosis evidence + deterministic R0/R1 YAML template

Run exactly:

```bash
<python> scripts/run_case.py diagnosis --work-dir <work-dir>
```

This retrieves:

- every diagnosis card belonging to CMC1;
- every diagnosis card matching a detected NGS gene regardless of CMC;
- every germline card matching a detected NGS gene.

The same deterministic stage writes:

- `<work-dir>/diagnostic_evidence.md` — model-facing evidence;
- `<work-dir>/diagnostic_evidence.json` — private deterministic machine boundary;
- `<work-dir>/report-draft-dx.yaml` — deterministic R0-R1 drafting template generated from `<work-dir>/reporting-rules-dx.md`.

The template pre-supplies every rule ID, `omit`, `statements`, `text`, and `citation` field. Canonically fixed values such as R0.1 `omit: false` and `(no citation required)` are pre-populated. Do not model-read these outputs until Step 3.

## Step 3 — Diagnostic YAML draft and refined CMC

Use a fresh bounded model session. Read only:

- `workflows/diagnosis_first_v1/prompts/analyse_diagnosis.md`;
- `workflows/diagnosis_first_v1/prompts/citation_rules.md`;
- `<work-dir>/case.md`;
- `<work-dir>/case-major-categories.json`;
- `<work-dir>/diagnostic_evidence.md`;
- `<work-dir>/ngs-panel-scope.md`;
- `<work-dir>/reporting-rules-dx.md`;
- `<work-dir>/report-draft-dx.yaml`.

Modify only `<work-dir>/report-draft-dx.yaml`.

Requirements:

- preserve every deterministic rule ID and order;
- set `omit` using boolean semantics (`True`/`False` or `Yes`/`No` are accepted);
- keep at least one statement for every rule, including omitted rules;
- split independently citable facts into separate statement items;
- keep citation markers in the `citation` field, never in `text`;
- set top-level `refined_cmc` to exactly one canonical value from `case-major-categories.json`.

Validate and deterministically extract CMC2:

```bash
<python> scripts/workflow_runtime.py cmc --work-dir <work-dir>
```

The command must succeed. Its output CMC is CMC2. If repair is required, use only the validator error, the current YAML draft, `workflows/diagnosis_first_v1/prompts/citation_rules.md`, and `diagnostic_evidence.md`; do not inspect private JSON/tag maps, corpus files, or validator source.

## Step 4 — Downstream retrieval + deterministic remainder YAML template

First generate the rule view and branch state exactly:

```bash
<python> scripts/workflow_runtime.py remainder-rules --work-dir <work-dir>
```

Record the deterministic `CMC_CHANGED=yes|no` output as `<cmc-changed>`. The generated `<work-dir>/reporting-rules-remainder.md` contains R2-R5 when CMC is unchanged or R0-R5 when CMC changed.

Then run exactly:

```bash
<python> scripts/run_case.py downstream --work-dir <work-dir>
```

The same deterministic stage writes:

- `<work-dir>/bundle.json` — private machine boundary;
- `<work-dir>/downstream_evidence.md` — Step-5 model evidence;
- `<work-dir>/evidence.md` — deterministic combined evidence used only for final citation rendering;
- `<work-dir>/card-tags.json` — private tag deconvolution map;
- `<work-dir>/report-draft-remainder.yaml` — deterministic branch-specific YAML drafting template generated from `<work-dir>/reporting-rules-remainder.md`.

Downstream retrieval uses CMC2, not a refined disease:

- prognosis/biomarker: detected-gene cards in CMC2;
- treatment: detected-gene cards in CMC2 plus disease-matched geneless treatment cards;
- germline: detected-gene cards regardless of disease;
- if CMC1 != CMC2, diagnosis is additionally recalled from both CMC1 and CMC2, plus all detected-gene diagnosis cards.

When CMC is unchanged, `downstream_evidence.md` contains no diagnosis cards. When CMC changed, it contains the expanded diagnosis evidence above.

## Step 5 — Remainder YAML analysis

Use a fresh bounded model session.

Always read only:

- `workflows/diagnosis_first_v1/prompts/analyse_remainder.md`;
- `workflows/diagnosis_first_v1/prompts/citation_rules.md`;
- `<work-dir>/case.md`;
- `<work-dir>/downstream_evidence.md`;
- `<work-dir>/ngs-panel-scope.md`;
- `<work-dir>/reporting-rules-remainder.md`;
- `<work-dir>/report-draft-remainder.yaml`.

If `<cmc-changed>` is `no`, `<work-dir>/reporting-rules-remainder.md` already contains the completed `<work-dir>/report-draft-dx.yaml` injected as established patient-level diagnostic context. The remainder template contains only R2-R5. Do not separately re-read `report-draft-dx.yaml`.

If `<cmc-changed>` is `yes`, `report-draft-dx.yaml` is not injected into the remainder rule view and must not be read in this model step. The remainder template contains R0-R5; answer every rule again using the expanded Step-4 evidence. CMC2 is fixed and must not be changed or re-emitted.

Modify only `<work-dir>/report-draft-remainder.yaml`. Preserve every deterministic rule ID and order, retain at least one atomic statement per rule, and keep statement-level citations separate from `text`.

Validate exactly:

```bash
<python> scripts/workflow_runtime.py validate-remainder --work-dir <work-dir>
```

For citation repair, `downstream_evidence.md` is the only evidentiary file that may be re-read.

## Step 6 — Assemble, summarise and render final report

### Step 6A — Deterministic assembly and omission filtering

Run exactly:

```bash
<python> scripts/workflow_runtime.py assemble --work-dir <work-dir>
```

The command validates both model-completed YAML drafts against their rule views and permitted evidence, then creates:

- `<work-dir>/report-draft.yaml` — retained rule content only;
- `<work-dir>/report-summary.yaml` — deterministic section-oriented Step-6B template.

If CMC was unchanged, R0-R1 comes from the diagnosis draft and R2-R5 from the remainder. If CMC changed, the Step-5 R0-R5 remainder replaces the diagnosis draft.

**Before writing `report-draft.yaml`, the deterministic assembler removes every rule whose `omit` value normalises to true (`True`, `true`, `Yes`, or `yes`).** Omitted rules and their statements are therefore unavailable to Step 6B and cannot leak into the final report.

`report-summary.yaml` contains these fixed sections in final-report order:

- `detected_variants`;
- `diagnosis`;
- `prognosis`;
- `treatment`;
- `mrd`;
- `germline`.

Each section contains a deterministic `statements` template with separate `text` and `citation` fields pre-filled as empty quoted strings (`text: ""`, `citation: ""`).

### Step 6B — Structured final summarisation

Use a fresh bounded model session. Read only:

- `workflows/diagnosis_first_v1/prompts/format_report.md`;
- `workflows/diagnosis_first_v1/prompts/citation_rules.md`;
- `<format-prompt>`;
- `<work-dir>/report-draft.yaml`;
- `<work-dir>/report-summary.yaml`.

Modify only `<work-dir>/report-summary.yaml`.

- `report-draft.yaml` is the sole source of clinical report content and already excludes all omitted rules.
- Preserve the deterministic summary section names and structure.
- Write one complete report sentence per completed summary statement.
- Preserve statement-level provenance when merging or splitting source facts by setting each summary statement's `citation` field to the exact required source citation disposition.
- A section may contain zero statements. For a section with no reportable content, either leave its blank `text: ""` / `citation: ""` placeholder untouched or set `statements: []`.
- Do not create `report-final.md`, numeric citations, a bibliography, or Markdown headings in this model step.

### Step 6C — Deterministic final formatting and citation rendering

Run exactly:

```bash
<python> scripts/workflow_runtime.py render --work-dir <work-dir>
```

The renderer validates `report-summary.yaml` against retained `report-draft.yaml`, rejects unknown runtime tags, emits non-empty sections in canonical order without section headings, converts runtime card tags to report-local numeric citations, appends the deterministic bibliography, and atomically writes `<work-dir>/report-final.md`.

If rendering fails, repair only the specific Step-6B YAML defect reported by the validator using the declared Step-6B model inputs, then rerun the same command. Do not inspect private JSON/tag maps, corpus files, or validator source.

After successful rendering, do not otherwise modify `report-final.md`.

## Step 7 — Existing delivery behaviour

For all supported modes run exactly:

```bash
<python> scripts/package_run.py \
  --work-dir <work-dir> \
  --output <work-dir>/ngs-report-debug.zip
```

`package_run.py` reads `<work-dir>/workflow.json` and uses the artifact allowlist declared by diagnosis-first-v1; it never infers workflow identity from evidence files.

Mode-specific delivery remains:

- `ngs-report`: display `report-final.md` unchanged and return `ngs-report-debug.zip`.
- `nel-demo`: only after `report-final.md` exists, run `python validation/scripts/retrieve_cli.py MC <demo-example> --mode nel-demo > <work-dir>/demo-expected.md`; then display `<work-dir>/case.md`, the generated report, and `<work-dir>/demo-expected.md`, and return `ngs-report-debug.zip`. Do not use the marking criteria to alter workflow artifacts.
- `nel-validate`: do not run a marking model. Run exactly:

```bash
<python> validation/scripts/package_marking.py <validation-case> \
  --mode nel-validate \
  --report <work-dir>/report-final.md \
  --output <work-dir>/nel-validation-<validation-case>.zip
```

Return the external-marking ZIP and the separate debug ZIP. Do not model-read marking criteria or the marking prompt.

- `nel-validate-function`: do not run a marking model and do not model-read bundled marking criteria, `validation/case_functional_manifest.md`, or the marking prompt. Run exactly:

```bash
<python> validation/scripts/package_marking.py <validation-case> \
  --mode nel-validate-function \
  --report <work-dir>/report-final.md \
  --output <work-dir>/nel-validation-function-<validation-case>.zip
```

Return the functional external-marking ZIP and the separate debug ZIP. The functional manifest is never read or packaged by the runtime workflow.

- `nel-validate-brief`: do not run a marking model and do not model-read bundled marking criteria or the marking prompt. Run exactly:

```bash
<python> validation/scripts/package_marking.py <validation-case> \
  --mode nel-validate-brief \
  --report <work-dir>/report-final.md \
  --output <work-dir>/nel-validation-brief-<validation-case>.zip
```

Return the brief-suite external-marking ZIP and the separate debug ZIP.
