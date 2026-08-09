---
name: ngs-evidence-layer
description: Builds a deterministic evidence block or NGS report for a myeloid NGS case, supports automatic or manual diagnostic adjudication, and can run repository examples or validation cases.
---
# NGS evidence layer
## Purpose

Perform only the mode explicitly requested by the user:

- `evidence-block` — run Steps 0–5; diagnosis review is automatic (skip 3B). Return `<work-dir>/block.md`.
- `evidence-block manual` — run Steps 0–5; Step 3B requires user confirmation or revision. Return `<work-dir>/block.md`.
- `ngs-report` — run Steps 0–6; diagnosis review is automatic (skip 3B) and reporting follows Step 5 without stopping. Step 7 renders `<work-dir>/report-final.md` in chat.
- `evidence-to-report` — run Step 0, verify Step 5 outputs already exist, then run Steps 6A–6B only. Step 7 renders `<work-dir>/report-final.md` in chat.
- `nel-demo example <N>` — resolve one numbered repository example and run the same automatic Steps 0–6 as `ngs-report`; Step 7 displays the case, generated report, and matching expected behaviour. Do not read the expected file before `report-final.md` is complete.
- `nel-validate <case-id>` — retrieve one validation case without its marking criteria, run the same automatic Steps 0–6 as `ngs-report`, then in Step 7 retrieve the criteria and mark `report-final.md`.

Do not infer the mode from available files. The skill does not create, edit, audit, or incorporate evidence cards.

## Workflow

- Step 0 — deterministic/setup: establish workflow state and `<work-dir>`; record `<format-prompt>` when needed.
- Step 1A — model: capture the supplied clinical case verbatim in `case.md`.
- Step 1B — model: structure `case.md` into `case-input.json`.
- Step 2 — deterministic: retrieve diagnosis evidence into `step2.json`.
- Step 3A — model: adjudicate the diagnosis into `adjudication.json`; automatic review also performs Step 3C (skip 3B).
- Step 3B — model/user: manual review only; finalise review fields in `adjudication.json`.
- Step 3C — model + deterministic append: append one integrated-diagnosis sentence to `case.md` without model-reading `case.md`; automatic review performs this in Step 3A, manual review after Step 3B.
- Steps 3D–5 — deterministic: validate the completed adjudication, retrieve the full evidence bundle into `bundle.json`, and render `block.md`.
- Step 6A — model: audit every reporting rule and write only reportable statements into `report-draft.md`.
- Step 6B — model: format `report-draft.md` into `report-final.md`.
- Step 7 — post-report delivery; for `nel-validate`, retrieve evaluator-only inputs and mark `report-final.md`.

`evidence-to-report` skips Steps 1A–5 after Step 0 verifies `<work-dir>/case.md` and a non-empty `<work-dir>/block.md` exist. Do not rerun skipped steps.


## Mandatory file-access policy

File access is **deny by default**.

- In each model step, read only its declared model-readable inputs.
- A path may be selected or recorded without permission to read its contents.
- Do not list or search directories or inspect undeclared files.
- Do not supplement inputs with live sources, external tools, or model knowledge.
- Do not carry information between bounded model steps unless supplied as an allowed input.
- Deterministic commands may read what their command requires; this does not make those files model-readable.
- Run only the commands declared below and write only the declared outputs.
- Do not modify an output written by a deterministic command.
- If a required input is missing, unreadable, malformed, or inconsistent with its contract, stop and report the error. Do not infer or replace it.
- For `nel-validate`, do not model-read `validation/case_summary.md`, `validation/marking_prompt.md`, or marking criteria before Step 7.

## Step 0 — Establish workflow state

### Required action

1. Select the explicit operating mode before reading case-specific inputs.
   - For `nel-demo example <N>`, require one integer `N` from 1 through 6 and run exactly:

     ```bash
     python scripts/resolve_demo.py <N>
     ```

   - Record the command's first output line as `<demo-case>` and second as `<demo-expected>`.
   - Do not read either file in Step 0.
   - For `nel-validate <case-id>`, require one case variant identifier such as `1A` and record it as `<validation-case>`. Do not retrieve the case or read any validation file in Step 0.
2. Establish `<work-dir>`:
   - if the user supplies a directory, resolve it to an absolute path and create it if necessary;
   - otherwise, except for `evidence-to-report`, run exactly:

     ```bash
     python scripts/create_work_dir.py
     ```

     Treat its single output line as `<work-dir>`. Do not substitute another directory.
   - for `evidence-to-report`, the user must supply or identify the working directory. Do not search for one.
3. Fail if `<work-dir>` is not a directory or is unreadable or unwritable. Do not fall back to another directory.
4. Print:

   ```text
   Working directory: <absolute-path>
   ```

5. For `ngs-report`, `evidence-to-report`, `nel-demo`, and `nel-validate`, record `<format-prompt>`:
   - default: `prompts/formatting/default.md`;
   - if the user explicitly specifies another file from `prompts/formatting/`, record that path;
   - do not list or search `prompts/formatting/`;
   - do not use a formatting prompt outside `prompts/formatting/`;
   - **record the path only. Do not read `<format-prompt>` until Step 6B.**
6. For `evidence-to-report`, verify only that `<work-dir>/case.md` exists and `<work-dir>/block.md` exists and is non-empty. Do not read their contents in Step 0.
7. Retain `<work-dir>` after success or failure. Do not clean it up automatically.

### Exit

- Operating mode is fixed.
- `<work-dir>` is fixed.
- If reporting is requested, `<format-prompt>` is fixed but unread.
- For `evidence-to-report`, the required Step 5 outputs exist.
- For `nel-demo`, `<demo-case>` and `<demo-expected>` are fixed but unread.
- For `nel-validate`, `<validation-case>` is fixed and validation files remain unread.

## Step 1A — Capture the case

Run only when Steps 1–5 are required.

For `nel-validate`, run exactly:

```bash
python validation/retrieve_cli.py case <validation-case> > <work-dir>/case.md
```

The command must succeed. Do not model-read `validation/case_summary.md` or any marking criteria. Proceed directly to Step 1B.

For all other modes, use a fresh bounded model session.

### Model-readable inputs

Read only the one case source:

- normal modes: the one user-designated case source;
- `nel-demo`: `<demo-case>`.

Do not read any other repository file in model Step 1A. In `nel-demo`, `<demo-case>` is the sole permitted repository-file exception.

### Required action

Identify the exact supplied content that constitutes the clinical case and write it to `<work-dir>/case.md`.

`case.md` must:
- contain only the supplied clinical case, preserving that content verbatim and in its original order;
- include all supplied patient, specimen, morphology, laboratory, cytogenetic, molecular, treatment, and other clinical case information;
- exclude workflow instructions, output requests, and other non-case commentary;
- contain no model interpretation, summary, normalisation, literature information, or added facts.

### Output

Write only `<work-dir>/case.md`.

## Step 1B — Structure the case

Use a fresh bounded model session.

### Model-readable inputs

Read only:

- `<work-dir>/case.md`;
- `schema/disease_vocabulary.json`.

Do not reread the original case source.

### Missing and unreported results

- Treat a reported test result as complete unless explicitly described as partial, selected, limited, abbreviated, pending, or otherwise incomplete.
- In a complete test, an unlisted abnormal finding is negative only within that test's scope.
- Do not assume that an unmentioned test was performed.
- A negative sequencing result does not exclude copy-number changes, rearrangements, or other findings unless the test assessed them.
- If cytogenetic results are not supplied, assume normal conventional cytogenetics for interpretation and record this as a `workflow_assumption`, not a patient result.
- Do not state that cytogenetics were performed or that a specific cytogenetic abnormality was formally excluded.
- Do not use the normal-cytogenetics assumption when supplied karyotype, FISH, copy-number, or other findings conflict with it.

### Required action

Create:

- `provisional_disease`
  - Use the supplied starting major diagnostic category as one exact allowed case-disease value from the vocabulary.
  - Do not upgrade it from model knowledge.
  - Use `no_haematological_malignancy` only when the case does not specify a haematological malignancy **and** the NGS result block contains no variants.
  - Do not use `no_haematological_malignancy` if variants are present.

- `genes`
  - Include only genes with reported variants in the NGS result block.
  - Exclude genes mentioned only in history, differential diagnosis, assay description, other tests, or lists of genes tested.
  - Use `[]` when no NGS variants are reported.

- `case_facts`
  - Preserve supplied patient facts losslessly with unique, stable `fact_id` values.
  - Preserve exact variants, values, units, morphology, blood counts, cytogenetic/FISH findings, treatment context, assay limitations, and qualifiers.
  - Do not strengthen or normalise supplied facts.
  - Do not infer phase, clonal order, allelic state, germline origin, assay coverage, or unreported clinical features.
  - Apply **Missing and unreported results** above.
  - Record one `test_result_status` fact for each supplied test treated as complete.
  - Do not create separate negative facts for every unlisted gene or abnormality.
  - Record an assumed normal cytogenetic result as a `workflow_assumption`, not a patient result.

### Output

Write JSON only to `<work-dir>/case-input.json` with exactly these top-level fields:

```json
{
  "provisional_disease": "<allowed case disease>",
  "genes": [],
  "case_facts": []
}
```

Do not add explanatory prose or other top-level fields.

## Step 2 — Retrieve diagnosis evidence

### Entry

`<work-dir>/case-input.json` exists.

### Command

Run exactly:

```bash
python scripts/run_case.py diagnosis --work-dir <work-dir>
```

### Exit

- The command succeeds.
- `<work-dir>/step2.json` exists.

Do not read or modify `step2.json` in this step.

## Step 3 — Adjudicate the diagnosis

### Step 3A — Model adjudication

Use a fresh bounded model session.

#### Model-readable inputs

Read only:

- `prompts/diagnostic_adjudication_prompt.md`;
- `<work-dir>/step2.json`.

#### Required action

Follow `prompts/diagnostic_adjudication_prompt.md` exactly, using `step2.json` as the complete patient-fact and diagnosis-evidence boundary.

If `diagnosis_cards` is empty:

- do not reclassify;
- set `status` to `"indeterminate"`;
- preserve `provisional_disease` as both `refined_disease` and `downstream_filter_disease`;
- set `diagnostic_label` to null;
- set `driven_by` and `criterion_assessment` to `[]`;
- state in `reason` that no corpus diagnosis evidence was retrieved.

For `evidence-block`, `ngs-report`, `nel-demo`, and `nel-validate`:
- set `user_review` to `"automatic"`;
- use the model adjudication as final;
- keep `downstream_filter_disease` equal to `refined_disease`;
- do not ask for user confirmation;
- perform Step 3C in this same model session (skip Step 3B).

For `evidence-block manual`:
- write the initial `<work-dir>/adjudication.json` with `user_review.decision: "pending"`;
- proceed to Step 3B.

#### Output

Write only `<work-dir>/adjudication.json` using the adjudication fields allowed by `prompts/diagnostic_adjudication_prompt.md` and the mode-specific `user_review` state above.

### Step 3B — Manual user review

Run only for `evidence-block manual`.

Use a fresh bounded model session.

#### Model-readable inputs

Read only:

- `<work-dir>/adjudication.json`;
- the user's agree/disagree response and, when disagreeing, supplied revised diagnosis.

Do not reread `step2.json`, the adjudication prompt, `case.md`, or any other file.

#### Required action

1. Present the proposed integrated diagnosis and one concise evidence-bounded argument, or a short list for several distinct reasons, before requesting the user's decision.
2. Ask the user to agree or disagree.
3. After the user's response, update only `user_review` and `downstream_filter_disease`:
   - **agree:** set `decision` to `"agree"` and copy the model's `diagnostic_label` and `refined_disease` exactly;
   - **disagree:** require a revised diagnostic label and one exact downstream category, then set `decision` to `"disagree"`; the Steps 3D–5 command will validate that category against Step 2.
4. Do not alter the model's original top-level adjudication fields after user review.
5. Set `downstream_filter_disease` to `user_review.refined_disease`.
6. Do not require a separate continuation word.

#### Output

Update only `<work-dir>/adjudication.json`.

### Step 3C — Append the integrated diagnosis

This step is compulsory for all modes that run Step 3.

For automatic review, perform Step 3C in the Step 3A model session (skip Step 3B), using the already-read `step2.json` and the `adjudication.json` just written. Do not reread them.

For completed manual review, use a fresh bounded model session and read only:

- `<work-dir>/step2.json`;
- `<work-dir>/adjudication.json`.

**Do not read `<work-dir>/case.md`.** The deterministic append command may access it.

#### Required action

Determine the final integrated diagnosis from the completed adjudication:
- automatic review: use the final top-level `diagnostic_label`; if null, use `downstream_filter_disease`;
- completed manual review: use `user_review.diagnostic_label`; if null, use `user_review.refined_disease`.

Create a specific reason of 20 words or fewer using only the allowed inputs. Use one supporting diagnosis-card citation as `<Author et al, year>`. If no diagnosis card supports the final integrated diagnosis, use `no citation required`.

Run exactly:

```bash
python scripts/append_integrated_diagnosis.py \
  --case <work-dir>/case.md \
  --diagnosis "<final integrated diagnosis>" \
  --reason "<specific reason, 20 words or fewer>" \
  --citation "<Author et al, year OR no citation required>"
```

Do not otherwise modify `case.md`.

#### Exit

The command succeeds and appends exactly one sentence:

`Integrated diagnosis: <diagnosis>, based on <specific reason, 20 words or fewer>. (<Author et al, year>).`

### Steps 3D–5 — Validate, retrieve and render

This deterministic command is **compulsory** after Step 3C.

Run exactly:

```bash
python scripts/run_case.py full --work-dir <work-dir>
```

#### Exit

- The command succeeds. If validation fails, stop.
- `<work-dir>/bundle.json` and `<work-dir>/block.md` exist.

Do not model-read or modify `step2.json`, `adjudication.json`, `bundle.json`, or `block.md` in Steps 3D–5.

Do not create a separate review, approval, diagnosis, or override file.

## Step 6 — Write the NGS report

Run only for `ngs-report`, `evidence-to-report`, `nel-demo`, or `nel-validate`.

For `ngs-report`, `nel-demo`, and `nel-validate`, begin Step 6A immediately after Step 5 succeeds. Do not stop for user input.

For `evidence-to-report`, Step 0 already verified `<work-dir>/case.md` and a non-empty `<work-dir>/block.md`; do not rerun Steps 1A–5.

### Step 6A — Sparse reporting-rule audit

Use a fresh bounded model session.

#### Model-readable inputs

Read only:

- `<work-dir>/case.md`;
- `<work-dir>/block.md`;
- `rules/agreed_reporting_rules.md`.

If any required input is missing, unreadable, or malformed, stop and report the error.

#### Source hierarchy

- **`case.md`:** sole source of truth for patient identity, specimen information, clinical context, test results, variants, measurements, other patient-specific facts, and the final integrated diagnosis.
- Use the `Integrated diagnosis:` sentence in `case.md` as the final diagnosis. Do not re-adjudicate it in Step 6A.
- **`block.md`:** exclusive source for literature-derived classification, prognosis, treatment, biomarkers, germline interpretation, clinical associations, and references.
- **Reporting rules:** questions and constraints to apply; they do not establish patient facts or clinical assertions.
- Do not strengthen, reconcile, or resolve interpretations beyond `block.md`.
- Preserve material uncertainty, disagreement, limitations, and qualifiers.
- Do not copy workflow metadata into the report draft unless a reporting rule requires it.
- If `case.md` and `block.md` conflict, do not silently repair the inconsistency.

#### Required action

Evaluate every numbered rule under R1–R5 in `rules/agreed_reporting_rules.md`. Every rule number must appear exactly once in `report-draft.md`.

For each rule that yields a reportable case-specific statement under its own instructions:

- identify it by rule number;
- give a 1–3 sentence case-specific answer;
- end every sentence with one citation marker:
  - one or more supporting citations in parentheses, e.g. `(Smith et al, 2024; Jones et al, 2023)`; or
  - `(no citation required)`;
- use only literature citations supported by `block.md`;
- use `(no citation required)` only when the sentence does not require literature support.

For every remaining rule, do not write an explanatory sentence. List its rule number under a single `No reportable statement` heading. This includes rules that are not applicable or yield a negative result unless that rule itself requires the negative result to be reported.

Do not omit any rule number because it is unlikely to appear in the final report.

#### Output

Write only:

`<work-dir>/report-draft.md`

### Step 6B — Format the final report

Use a fresh bounded model session.

#### Model-readable inputs before `report-final.md` is complete

Read only:

- `<format-prompt>`;
- `<work-dir>/report-draft.md`.

Do not read `case.md`, `block.md`, `rules/agreed_reporting_rules.md`, the original case document, or any other file. Do not use information carried from Step 6A except `report-draft.md`.

If either required input is missing, unreadable, or malformed, stop and report the error.

#### Required action

Follow `<format-prompt>` exactly, using `report-draft.md` as the sole source of report content.

Do not introduce a clinical assertion, qualification, citation, or patient fact that is absent from `report-draft.md`.

#### Output

Write only:

`<work-dir>/report-final.md`

The file must contain the final report only. Do not include process commentary, rule numbers, source-audit notes, confidence commentary, alternative drafts, or an additional summary.

## Step 7 — Post-report delivery and validation

Run after `report-final.md` is complete.

- For `ngs-report` and `evidence-to-report`, display `<work-dir>/report-final.md` in chat unchanged without another model session.
- For `nel-demo`, only now read `<demo-case>` and `<demo-expected>`; this is the first point permitted to read `<demo-expected>`. Display the case, `<work-dir>/report-final.md`, and expected behaviour unchanged. Do not use `<demo-expected>` to alter any workflow artifact.
- For `nel-validate`, run exactly:

  ```bash
  python validation/retrieve_cli.py case <validation-case> > <work-dir>/validation-case.md
  python validation/retrieve_cli.py MC <validation-case> > <work-dir>/marking-criteria.md
  ```

  Both commands must succeed. Then use a fresh bounded model session and read only:
  - `<validation-case>`;
  - `validation/marking_prompt.md`;
  - `<work-dir>/validation-case.md`;
  - `<work-dir>/report-final.md`;
  - `<work-dir>/marking-criteria.md`;
  - `<work-dir>/block.md`.

  Follow `validation/marking_prompt.md` exactly. Treat `report-final.md` as the candidate answer and write only `<work-dir>/validation-mark.md`. Do not alter any earlier workflow artifact.

Display mode outputs in these forms:

```text
nel-demo:
## Case
<demo-case contents>
## NEL report
<work-dir>/report-final.md contents
## Expected
<demo-expected contents>

nel-validate:
## Case
<work-dir>/validation-case.md contents
## NEL report
<work-dir>/report-final.md contents
## Validation
<work-dir>/validation-mark.md contents
```

## Final delivery contract

Deliver only the artifact or artifacts explicitly requested by the user.

### Evidence-block mode

For `evidence-block` and `evidence-block manual`, return `<work-dir>/block.md` unchanged.

### NGS-report mode

For `ngs-report` and `evidence-to-report`, Step 7 performs final delivery by rendering `<work-dir>/report-final.md` in chat unchanged.

Do not also return `block.md` unless explicitly requested and do not perform an additional rendering pass after Step 7.

### Demo mode

For `nel-demo`, Step 7 performs final delivery by rendering the case, `<work-dir>/report-final.md`, and expected behaviour. Do not read or render `<demo-expected>` before `report-final.md` is complete and do not perform an additional rendering pass after Step 7.

Do not return `block.md` unless explicitly requested.

### Validation mode

For `nel-validate`, Step 7 renders the validation case, `<work-dir>/report-final.md`, and `<work-dir>/validation-mark.md`. Do not retrieve or read marking criteria before `report-final.md` is complete.

Do not return `block.md` unless explicitly requested.

### Both outputs explicitly requested

Use `ngs-report` and return separately:

1. `<work-dir>/block.md`;
2. `<work-dir>/report-final.md`.

Do not combine them.
