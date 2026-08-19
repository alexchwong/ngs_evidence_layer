---
name: ngs-evidence-layer-categorical-v1
description: Categorical diagnosis-first workflow for ngs-report, nel-demo, nel-validate, nel-validate-function, and nel-validate-brief.
---
# NGS evidence layer — categorical-v1

## Scope

Supported modes only:

- `ngs-report`
- `nel-demo example <N>`
- `nel-validate <case-id>`
- `nel-validate-function <case-id>`
- `nel-validate-brief <case-id>`

This workflow clones the diagnosis-first-v1 evidence/retrieval pipeline but changes diagnosis handoff and final report synthesis. Environment setup is owned by Step 0; after Step 0 defines `<python>`, use it for every deterministic command in this workflow.

The workflow is:

0. setup;
1. capture/structure case and assign Step-1 case major category (CMC1);
2. retrieve broad diagnosis + gene-matched germline evidence and deterministically generate the R0-R1 YAML draft template;
3. model-complete R0-R1 in `report-draft-dx.yaml`, set refined CMC (CMC2), then independently synthesize an integrated <=70-word diagnosis in `report-summary-dx.yaml`;
4. generate the branch-specific rule view, injecting `report-summary-dx.yaml` only when CMC is unchanged, then retrieve/render downstream evidence and generate the remainder YAML template;
5. model-complete R2-R5, or R0-R5 again when CMC changed;
6. deterministically assemble retained rules and a category manifest, draft each required final category in a separate bounded model session, assemble `report-summary.yaml`, then render citations and final Markdown;
7. use the existing delivery/validation behaviour and packager command.

The final report has five possible categories in order: diagnosis, prognosis, treatment, MRD markers, and germline. There is no separate detected-variants category; detected variants are integrated into diagnosis. Categories with no `omit: false` source rules are skipped deterministically before any model call.

`downstream_filter_disease` is not used. CMC2 is the downstream disease-routing value.

## Global access/model rules

File access is deny-by-default. In each model step read only the files explicitly declared below. Deterministic commands may read their required inputs but do not make those inputs model-readable. Do not inspect deterministic Python source while running the workflow. Use a fresh bounded model session for each model step; Step 6B additionally requires a fresh session for each individual category.

Shared patient-result semantics from diagnosis-first-v1 apply to Steps 1B, 3 and 5: treat explicitly complete tests as complete within their stated scope; do not assume unmentioned tests; if cytogenetics are absent, normal conventional cytogenetics may be used only as a workflow assumption and must not be stated as a performed negative test.

For Steps 3 and 5, `<work-dir>/ngs-panel-scope.md` is the complete assay-scope boundary for gene-level NGS negative inference. When the patient NGS result is complete, a gene listed in that file but absent from the detected-variant list is negative only for the variant classes stated in the panel-scope file. Use that negative result to resolve reporting-rule criteria and exclusions; do not treat the gene as unresolved merely because it is not individually listed. Do not call this whole-gene biological wild type or extend the inference to unlisted variant classes.

For rule drafting, the workflow-local REPORT/OMIT taxonomy is encoded in YAML as:

- REPORT -> `omit: false` or `omit: No`;
- OMIT -> `omit: true` or `omit: Yes`.

Every rule must still contain at least one atomic statement. Omission controls downstream inclusion only.

## Step 0 — Setup

Select the explicit mode before reading case-specific inputs.

At Step 0 only, prepare the repository-local Python environment before running workflow setup:

```bash
python3 -m venv .env
.env/bin/python -m pip install -r requirements.txt
```

Set `<python>` to `.env/bin/python`. The requirements install must succeed; categorical YAML tooling requires `PyYAML>=6.0`. Do not run this bootstrap from the root router or from legacy-v1.

Choose `<setup-work-arg>` exactly once:

- supplied directory: `--work-dir <supplied-directory>`;
- exact `->project` modifier: `--project`;
- otherwise empty.

Run exactly one setup command:

```bash
# ngs-report
<python> scripts/setup_workflow.py --workflow categorical-v1 --mode ngs-report <setup-work-arg>

# nel-demo example <N>
<python> scripts/setup_workflow.py --workflow categorical-v1 --mode nel-demo --example <N> <setup-work-arg>

# nel-validate <case-id>
<python> scripts/setup_workflow.py --workflow categorical-v1 --mode nel-validate --case-id <case-id> <setup-work-arg>

# nel-validate-function <case-id>
<python> scripts/setup_workflow.py --workflow categorical-v1 --mode nel-validate-function --case-id <case-id> <setup-work-arg>

# nel-validate-brief <case-id>
<python> scripts/setup_workflow.py --workflow categorical-v1 --mode nel-validate-brief --case-id <case-id> <setup-work-arg>
```

Record output line 1 as `<work-dir>` and print `Working directory: <absolute-path>`.

For `nel-demo`, record output line 2 as `<demo-case>` and line 3 as `<demo-expected>`; do not read either yet. For validation modes, record `<validation-case>` as supplied. Setup writes `<work-dir>/case.md`; do not read validation marking files.

Setup also creates:

- `<work-dir>/case-major-categories.json`;
- `<work-dir>/ngs-panel-scope.md`;
- `<work-dir>/reporting-rules-dx.md` containing R0-R1 only.

## Step 1 — Case capture and CMC1

### Step 1A

For `nel-validate`, `nel-validate-function`, and `nel-validate-brief`, Step 0 already wrote `<work-dir>/case.md`; do not run a second retrieval command and do not read marking inputs.

For other modes, use a fresh model session and read only `prompts/workflow/capture_case.md` plus the designated case source (`<demo-case>` for demo). Write only `<work-dir>/case.md`.

### Step 1B

Use a fresh model session. Read only:

- `prompts/workflow/structure_case.md`;
- `<work-dir>/case.md`;
- `<work-dir>/case-major-categories.json`.

Write only `<work-dir>/case-input.json`. Its `case_major_category` is CMC1.

## Step 2 — Diagnosis evidence + R0/R1 YAML template

Run exactly:

```bash
<python> scripts/run_case.py diagnosis --work-dir <work-dir>
```

This writes:

- `<work-dir>/diagnostic_evidence.md`;
- `<work-dir>/diagnostic_evidence.json` — private deterministic boundary;
- `<work-dir>/report-draft-dx.yaml` — deterministic R0-R1 drafting template.

## Step 3 — Diagnostic YAML draft, refined CMC and integrated diagnosis summary

### Step 3A — R0/R1 analysis

Use a fresh bounded model session. Read only:

- `workflows/categorical_v1/prompts/analyse_diagnosis.md`;
- `workflows/categorical_v1/prompts/citation_rules.md`;
- `<work-dir>/case.md`;
- `<work-dir>/case-major-categories.json`;
- `<work-dir>/diagnostic_evidence.md`;
- `<work-dir>/ngs-panel-scope.md`;
- `<work-dir>/reporting-rules-dx.md`;
- `<work-dir>/report-draft-dx.yaml`.

Modify only `<work-dir>/report-draft-dx.yaml`. Preserve every deterministic rule ID/order, use boolean omission semantics, retain at least one atomic statement per rule, keep citation markers in `citation`, and set `refined_cmc` to exactly one canonical CMC.

Validate and extract CMC2:

```bash
<python> scripts/workflow_runtime.py cmc --work-dir <work-dir>
```

If repair is required, use only the validator error, current YAML, categorical citation rules, and `diagnostic_evidence.md`.

### Step 3B — Integrated diagnosis synthesis

Create the deterministic diagnosis-summary template:

```bash
<python> scripts/workflow_runtime.py prepare-dx-summary --work-dir <work-dir>
```

Use a fresh bounded model session. Read only:

- `workflows/categorical_v1/prompts/format_report.md`;
- `workflows/categorical_v1/prompts/citation_rules.md`;
- `workflows/categorical_v1/prompts/formatting/diagnosis.md`;
- `<work-dir>/case.md`;
- `<work-dir>/report-draft-dx.yaml`;
- `<work-dir>/report-summary-dx.yaml`.

Modify only `<work-dir>/report-summary-dx.yaml`.

The diagnosis summary is a cohesive synthesis of the reportable R0/R1 content, not a sentence-by-sentence shortening exercise. It must use full sentences, contain no more than 70 words in total, and answer: what variants were detected; what is the integrated diagnosis; and what patient-level facts support it. Consider every `omit: false` R0/R1 statement and preserve every clinically distinct retained fact needed to keep its meaning. Do not restore `omit: true` material.

Validate exactly:

```bash
<python> scripts/workflow_runtime.py validate-dx-summary --work-dir <work-dir>
```

## Step 4 — Downstream retrieval + remainder YAML template

Generate branch state and rule view:

```bash
<python> scripts/workflow_runtime.py remainder-rules --work-dir <work-dir>
```

Record `CMC_CHANGED=yes|no` as `<cmc-changed>`.

- If unchanged, `reporting-rules-remainder.md` contains R2-R5 and the validated `report-summary-dx.yaml` injected as established diagnostic context.
- If changed, it contains R0-R5 and **does not inject `report-summary-dx.yaml`**; the Step-3 diagnosis is potentially stale.

Then run:

```bash
<python> scripts/run_case.py downstream --work-dir <work-dir>
```

This writes:

- `<work-dir>/bundle.json` — private;
- `<work-dir>/downstream_evidence.md`;
- `<work-dir>/evidence.md` — final citation rendering only;
- `<work-dir>/card-tags.json` — private;
- `<work-dir>/report-draft-remainder.yaml`.

Downstream retrieval uses CMC2. Prognosis/biomarker retrieval is detected-gene + CMC2; treatment also permits disease-matched geneless treatment cards; germline is detected-gene regardless of disease; changed-CMC runs additionally recall diagnosis evidence from both CMCs and detected-gene diagnosis cards.

## Step 5 — Remainder YAML analysis

Use a fresh bounded model session. Always read only:

- `workflows/categorical_v1/prompts/analyse_remainder.md`;
- `workflows/categorical_v1/prompts/citation_rules.md`;
- `<work-dir>/case.md`;
- `<work-dir>/downstream_evidence.md`;
- `<work-dir>/ngs-panel-scope.md`;
- `<work-dir>/reporting-rules-remainder.md`;
- `<work-dir>/report-draft-remainder.yaml`.

If `<cmc-changed>` is `no`, the rule view already contains `report-summary-dx.yaml` as established context and the template contains only R2-R5. Do not separately re-read the diagnosis draft or diagnosis summary.

If `<cmc-changed>` is `yes`, no Step-3 diagnosis summary is injected and the template contains R0-R5. Answer every rule again from expanded evidence. CMC2 is fixed and must not be changed or re-emitted.

Modify only `<work-dir>/report-draft-remainder.yaml`. Validate:

```bash
<python> scripts/workflow_runtime.py validate-remainder --work-dir <work-dir>
```

For citation repair, `downstream_evidence.md` is the only evidentiary file that may be re-read.

## Step 6 — Category-isolated final synthesis and rendering

### Step 6A — Deterministic retained-rule assembly and category manifest

Run exactly:

```bash
<python> scripts/workflow_runtime.py prepare-categories --work-dir <work-dir>
```

This validates the completed rule drafts, removes every `omit: true` rule, and writes:

- `<work-dir>/report-draft.yaml` — all retained R0-R5 content;
- `<work-dir>/report-summary-manifest.yaml` — CMC branch plus per-category status, source rule IDs, word limit and artifact;
- `<work-dir>/report-summary-diagnosis.yaml`;
- `<work-dir>/report-summary-prognosis.yaml`;
- `<work-dir>/report-summary-treatment.yaml`;
- `<work-dir>/report-summary-mrd.yaml`;
- `<work-dir>/report-summary-germline.yaml`.

For any category with zero retained (`omit: false`) source rules, the manifest status is `omitted_no_reportable_rules`, its YAML has `statements: []`, and **no model call is permitted**.

If CMC is unchanged, the diagnosis category is deterministically copied from the already validated `report-summary-dx.yaml`; its manifest status is `reused_diagnosis_summary` and it is not redrafted.

If CMC changed, diagnosis is sourced from the final retained R0/R1 content and is drafted in Step 6B like any other required category.

### Step 6B — Draft each required category separately

Categories are processed independently in this order: diagnosis, prognosis, treatment, mrd, germline. For each category whose manifest status is `pending_model_draft`, use a **new fresh bounded model session** and read only:

- `workflows/categorical_v1/prompts/format_report.md`;
- `workflows/categorical_v1/prompts/citation_rules.md`;
- `workflows/categorical_v1/prompts/formatting/<category>.md`;
- `<work-dir>/case.md`;
- `<work-dir>/case-input.json`;
- `<work-dir>/report-draft.yaml`;
- `<work-dir>/report-draft-remainder.yaml`;
- `<work-dir>/report-summary-manifest.yaml`;
- `<work-dir>/report-summary-<category>.yaml`;
- **only when CMC is unchanged:** `<work-dir>/report-summary-dx.yaml`.

Thus every drafted paragraph receives full patient context, the complete remainder-rule answers, and the established integrated diagnosis when it remains valid. `report-draft.yaml` is the authoritative reportable-content boundary; any `omit: true` lines still visible in `report-draft-remainder.yaml` are context only and must not be resurrected.

Modify only that category's YAML. Each category is answered in isolation:

- `diagnosis` (CMC changed only): variants detected + integrated diagnosis + supporting facts; maximum 70 words;
- `prognosis`: how each reportable NGS result affects prognosis in this patient; maximum 50 words;
- `treatment`: how treatment may be affected by the NGS result(s), if any; maximum 50 words;
- `mrd`: available molecular MRD markers and relevant limitations, if any; maximum 50 words;
- `germline`: potential germline variants in demographic, symptom and laboratory context; maximum 50 words.

After each drafted category, validate exactly with the corresponding command:

```bash
<python> scripts/workflow_runtime.py validate-category-diagnosis --work-dir <work-dir>
<python> scripts/workflow_runtime.py validate-category-prognosis --work-dir <work-dir>
<python> scripts/workflow_runtime.py validate-category-treatment --work-dir <work-dir>
<python> scripts/workflow_runtime.py validate-category-mrd --work-dir <work-dir>
<python> scripts/workflow_runtime.py validate-category-germline --work-dir <work-dir>
```

Run only the validation command for the category just drafted. Do not invoke a model for manifest statuses `omitted_no_reportable_rules` or `reused_diagnosis_summary`. The deterministic validator updates successful `pending_model_draft` entries to `drafted`.

### Step 6C — Deterministic summary assembly and final citation rendering

After all required category drafts validate, run:

```bash
<python> scripts/workflow_runtime.py assemble-summary --work-dir <work-dir>
```

This refuses to assemble while any category remains `pending_model_draft` and writes `<work-dir>/report-summary.yaml` from the five independently validated category artifacts.

Then run:

```bash
<python> scripts/workflow_runtime.py render --work-dir <work-dir>
```

The renderer emits only non-empty categories in canonical order, without headings, converts runtime card tags to report-local numeric citations, appends the deterministic bibliography, and atomically writes `<work-dir>/report-final.md`.

If rendering fails, repair only the specific category-summary YAML defect reported by the validator using that category's declared Step-6B inputs, revalidate the category, rerun `assemble-summary`, then rerun `render`. Do not inspect private JSON/tag maps, corpus files, or validator source.

After successful rendering, do not otherwise modify `report-final.md`.

## Step 7 — Existing delivery behaviour

For all supported modes run exactly:

```bash
<python> scripts/package_run.py \
  --work-dir <work-dir> \
  --output <work-dir>/ngs-report-debug.zip
```

`package_run.py` reads `<work-dir>/workflow.json` and packages the categorical-v1 artifact allowlist.

Mode-specific delivery remains:

- `ngs-report`: display `report-final.md` unchanged and return `ngs-report-debug.zip`.
- `nel-demo`: only now read `<demo-case>` and `<demo-expected>`; display case, generated report and expected behaviour, and return `ngs-report-debug.zip`.
- `nel-validate`: do not run a marking model. Run:

```bash
<python> validation/package_marking.py <validation-case> \
  --report <work-dir>/report-final.md \
  --output <work-dir>/nel-validation-<validation-case>.zip
```

Return the external-marking ZIP and debug ZIP. Do not model-read marking criteria or marking prompt.

- `nel-validate-function`: do not run a marking model and do not model-read functional marking inputs. Run:

```bash
<python> validation/package_marking.py <validation-case> \
  --case-file validation/case_functional.md \
  --report <work-dir>/report-final.md \
  --output <work-dir>/nel-validation-function-<validation-case>.zip
```

Return the external-marking ZIP and debug ZIP.

- `nel-validate-brief`: do not run a marking model and do not model-read brief-suite marking inputs. Run:

```bash
<python> validation/package_marking.py <validation-case> \
  --case-file validation/validation_brief.md \
  --report <work-dir>/report-final.md \
  --output <work-dir>/nel-validation-brief-<validation-case>.zip
```

Return the brief-suite external-marking ZIP and debug ZIP.
