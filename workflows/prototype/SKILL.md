---
name: ngs-evidence-layer-0.2.2-prototype
description: Parallel diagnosis-first prototype for ngs-report, nel-demo, nel-validate, and nel-validate-function benchmarking.
---
# NGS evidence layer — 0.2.2 diagnosis-first prototype

## Scope

Supported modes only:

- `ngs-report`
- `nel-demo example <N>`
- `nel-validate <case-id>`
- `nel-validate-function <case-id>`

This prototype is parallel to the legacy workflow. Do not modify or substitute with the original workflow prompt.

The workflow is:

0. setup;
1. capture/structure case and assign Step-1 case major category (CMC1);
2. retrieve broad diagnosis + gene-matched germline evidence using the R0-R1 rule view generated at setup;
3. model-answer R0-R1 in `report-draft-dx.md` and emit one terminal refined CMC (CMC2);
4. retrieve/render downstream evidence using CMC2 and generate the Step-5 rule subset;
5. model-answer the remainder, or all R0-R5 again when CMC changed;
6. deterministically assemble `report-draft.md`, then format/render citations;
7. use the existing delivery/validation behaviour and packager command.

`downstream_filter_disease` is not used in this prototype. CMC2 is the downstream disease-routing value.

## Global access/model rules

File access is deny-by-default. In each model step read only the files explicitly declared below. Deterministic commands may read their required inputs but do not make those inputs model-readable. Do not inspect deterministic Python source while running the workflow. Use a fresh bounded model session for each model step and do not carry information between model steps unless an allowed input supplies it.

Shared patient-result semantics from the original workflow apply to Steps 1B, 3 and 5: treat explicitly complete tests as complete within their stated scope; do not assume unmentioned tests; if cytogenetics are absent, normal conventional cytogenetics may be used only as a workflow assumption and must not be stated as a performed negative test.

## Step 0 — Setup

Select the explicit mode before reading case-specific inputs.

Choose the setup work-directory argument exactly once:

- supplied directory: `<setup-work-arg>` is `--work-dir <supplied-directory>`;
- exact `->project` modifier: `<setup-work-arg>` is `--project`;
- otherwise: `<setup-work-arg>` is empty.

Run exactly one prototype setup command for the selected mode:

```bash
# ngs-report
python scripts/prototype_workflow.py setup --mode ngs-report <setup-work-arg>

# nel-demo example <N>
python scripts/prototype_workflow.py setup --mode nel-demo --example <N> <setup-work-arg>

# nel-validate <case-id>
python scripts/prototype_workflow.py setup --mode nel-validate --case-id <case-id> <setup-work-arg>

# nel-validate-function <case-id>
python scripts/prototype_workflow.py setup --mode nel-validate-function --case-id <case-id> <setup-work-arg>
```

Record output line 1 as `<work-dir>` and print `Working directory: <absolute-path>`.

For `nel-demo`, also record output line 2 as `<demo-case>` and line 3 as `<demo-expected>`. Do not read either yet.

For `nel-validate <case-id>` or `nel-validate-function <case-id>`, record `<validation-case>` as the supplied case ID. Setup deterministically writes `<work-dir>/case.md`; do not read validation marking files. For `nel-validate-function`, `validation/case_functional.md` and `validation/case_functional_manifest.md` remain forbidden model inputs.

Setup also generates the two branch-independent procedural assets used later:

- `<work-dir>/case-major-categories.json`;
- `<work-dir>/reporting-rules-dx.md` containing only the prompt-owned R0-R1 diagnosis rule view.

Setup is additive for an existing directory. It may replace those two procedural assets, but it must not overwrite an existing `case.md` with different validation-case content or modify any later workflow draft.

For all supported modes record `<format-prompt>`; default `prompts/formatting/default.md`. Record the path only and do not read it until Step 6B.

## Step 1 — Case capture and CMC1

### Step 1A

For `nel-validate` and `nel-validate-function`, Step 0 has already written `<work-dir>/case.md` deterministically. Do not run a second case-retrieval command. Do not model-read `validation/case_functional.md`, `validation/case_functional_manifest.md`, or marking criteria.

For other modes, use a fresh model session and read only `prompts/workflow/capture_case.md` plus the designated case source (`<demo-case>` for demo). Write only `<work-dir>/case.md`.

### Step 1B

Use the `<work-dir>/case-major-categories.json` generated in Step 0. Do not regenerate it. Then use a fresh model session. Read only:

- `prompts/workflow/structure_case.md`;
- `<work-dir>/case.md`;
- `<work-dir>/case-major-categories.json`.

The model writes only `<work-dir>/case-input.json`. Its `case_major_category` is CMC1.

## Step 2 — Diagnosis evidence + R0/R1 rules

Run exactly:

```bash
python scripts/run_case.py prototype-diagnosis --work-dir <work-dir>
```

This retrieves:

- every diagnosis card belonging to CMC1;
- every diagnosis card matching a detected NGS gene regardless of CMC;
- every germline card matching a detected NGS gene.

It writes model-facing `<work-dir>/diagnostic_evidence.md` and a private deterministic machine boundary. Runtime card tags are derived from the same full blacklist-eligible card universe used later.

The diagnostic R0-R1 rule view was generated in Step 0 as `<work-dir>/reporting-rules-dx.md`; do not regenerate it here. It uses the prompt-owned diagnosis template under `workflows/prototype/prompts/rule_views/`, injects the shared `prompts/workflow/reporting_rule_policy.md`, and contains only canonical R0-R1 rules.

Do not model-read either output until Step 3.

## Step 3 — Diagnostic draft and refined CMC

Use a fresh bounded model session. Read only:

- `workflows/prototype/prompts/analyse_diagnosis_prototype.md`;
- `prompts/workflow/citation_rules.md`;
- `<work-dir>/case.md`;
- `<work-dir>/case-major-categories.json`;
- `<work-dir>/diagnostic_evidence.md`;
- `<work-dir>/reporting-rules-dx.md`.

Follow the prototype diagnosis prompt and the prompt-owned analysis contract rendered into `reporting-rules-dx.md`; apply the Rule-draft citation contract in `citation_rules.md`. Write only `<work-dir>/report-draft-dx.md`.

The final line must be exactly:

```text
REFINED_CMC: <canonical case major category>
```

Validate and deterministically extract CMC2:

```bash
python scripts/prototype_workflow.py cmc \
  --draft <work-dir>/report-draft-dx.md \
  --evidence <work-dir>/diagnostic_evidence.md \
  --rules <work-dir>/reporting-rules-dx.md
```

The command must succeed. Its output CMC is CMC2. If citation repair is required, use only the validator error, the current draft, `citation_rules.md`, and `diagnostic_evidence.md`; do not inspect private JSON/tag maps or corpus files.

## Step 4 — Downstream retrieval and Step-5 rule scope

First generate the rule view and branch state exactly. The generator renders the appropriate prompt-owned branch template under `workflows/prototype/prompts/rule_views/`, injects the shared reporting-rule policy, and then appends either canonical R2-R5 rules or canonical R0-R5 rules when CMC changed:

```bash
python scripts/prototype_workflow.py remainder-rules \
  --case-input <work-dir>/case-input.json \
  --diagnosis-draft <work-dir>/report-draft-dx.md \
  --output <work-dir>/reporting-rules-remainder.md
```

Record the deterministic `CMC_CHANGED=yes|no` output as `<cmc-changed>`.

Then run exactly:

```bash
python scripts/run_case.py prototype-downstream --work-dir <work-dir>
```

The command writes:

- `<work-dir>/bundle.json` — private machine boundary;
- `<work-dir>/downstream_evidence.md` — Step-5 model evidence;
- `<work-dir>/evidence.md` — deterministic union used only for final draft/citation validation;
- `<work-dir>/card-tags.json` — private tag deconvolution map.

Downstream retrieval uses CMC2, not a refined disease:

- prognosis/biomarker: detected-gene cards in CMC2;
- treatment: detected-gene cards in CMC2 plus disease-matched geneless treatment cards;
- germline: detected-gene cards regardless of disease;
- if CMC1 != CMC2, diagnosis is additionally recalled from **both CMC1 and CMC2**, plus all detected-gene diagnosis cards.

When CMC is unchanged, `downstream_evidence.md` contains no diagnosis cards. When CMC changed, it contains the expanded diagnosis evidence above.

## Step 5 — Remainder analysis

Use a fresh bounded model session.

Always read only:

- `workflows/prototype/prompts/analyse_remainder_prototype.md`;
- `prompts/workflow/citation_rules.md`;
- `<work-dir>/case.md`;
- `<work-dir>/downstream_evidence.md`;
- `<work-dir>/reporting-rules-remainder.md`.

If `<cmc-changed>` is `no`, additionally read `<work-dir>/report-draft-dx.md`. The rule file contains only R2-R5; answer only R2-R5.

If `<cmc-changed>` is `yes`, **do not read `report-draft-dx.md` in this model step**. The rule file contains R0-R5; answer every rule again using the expanded Step-4 evidence. CMC2 is fixed and must not be changed or re-emitted.

Follow the prompt-owned analysis contract rendered into `reporting-rules-remainder.md`; apply the Rule-draft citation contract in `citation_rules.md`. Write only `<work-dir>/report-draft-remainder.md`.

Validate exactly:

```bash
python scripts/report_audit.py validate \
  --draft <work-dir>/report-draft-remainder.md \
  --evidence <work-dir>/downstream_evidence.md \
  --rules <work-dir>/reporting-rules-remainder.md \
  --allow-no-evidence-tags
```

For citation repair, `downstream_evidence.md` is the only evidentiary file that may be re-read.

## Step 6 — Assemble and format final report

### Step 6A — Deterministic assembly

Run exactly:

```bash
python scripts/prototype_workflow.py assemble \
  --case-input <work-dir>/case-input.json \
  --diagnosis-draft <work-dir>/report-draft-dx.md \
  --remainder-draft <work-dir>/report-draft-remainder.md \
  --evidence <work-dir>/evidence.md \
  --output <work-dir>/report-draft.md
```

If CMC was unchanged, this concatenates R0-R1 from the diagnosis draft with R2-R5 from the remainder. If CMC changed, `report-draft.md` is the Step-5 R0-R5 replacement draft. The `REFINED_CMC:` line is never copied. The command validates the assembled draft against the complete canonical reporting rules and combined evidence.

### Step 6B — Format

Use a fresh bounded model session. Read only:

- `prompts/workflow/format_report.md`;
- `prompts/workflow/citation_rules.md`;
- `<format-prompt>`;
- `<work-dir>/report-draft.md`.

Write only `<work-dir>/report-final.md`. Do not run a separate citation-validation command here; Step 6C `render` performs the same strict validation before any write.

### Step 6C — Citation validation and rendering

Run exactly:

```bash
python scripts/report_citations.py render \
  --report <work-dir>/report-final.md \
  --evidence <work-dir>/evidence.md \
  --card-tags <work-dir>/card-tags.json
```

`render` first enforces the Step 6B citation invariant, including the requirement that every sentence-ending full stop is followed by exactly one citation disposition, and writes atomically only after validation succeeds.

If it fails, repair only from the renderer error plus the declared Step-6B model inputs, then rerun the same `render` command until it succeeds. Do not inspect private JSON/tag maps, corpus files, or validator source.

After a successful render, do not run `render` again and do not otherwise modify `report-final.md`. A second render is expected to fail safely because the successfully rendered report contains numeric citation markers rather than runtime card tags.

## Step 7 — Existing delivery behaviour

Step 7 behaviour is unchanged from original workflow.

For all supported modes run exactly:

```bash
python scripts/package_run.py \
  --work-dir <work-dir> \
  --output <work-dir>/ngs-report-debug.zip
```

`package_run.py` deterministically detects the prototype machine boundary and uses the prototype artifact allowlist; legacy workflow runs continue to use the legacy allowlist and CLI unchanged.

Mode-specific delivery remains:

- `ngs-report`: display `report-final.md` unchanged and return `ngs-report-debug.zip`.
- `nel-demo`: only now read `<demo-case>` and `<demo-expected>`; display case, generated report and expected behaviour, and return `ngs-report-debug.zip`.
- `nel-validate`: do not run a marking model. Run exactly:

```bash
python validation/package_marking.py <validation-case> \
  --report <work-dir>/report-final.md \
  --output <work-dir>/nel-validation-<validation-case>.zip
```

Return the external-marking ZIP and the separate debug ZIP. Do not model-read marking criteria or the marking prompt.
- `nel-validate-function`: do not run a marking model and do not model-read `validation/case_functional.md`, `validation/case_functional_manifest.md`, marking criteria, or the marking prompt. Run exactly:

```bash
python validation/package_marking.py <validation-case> \
  --case-file validation/case_functional.md \
  --report <work-dir>/report-final.md \
  --output <work-dir>/nel-validation-function-<validation-case>.zip
```

Return the functional external-marking ZIP and the separate debug ZIP. The functional manifest is never read or packaged by the runtime workflow.
