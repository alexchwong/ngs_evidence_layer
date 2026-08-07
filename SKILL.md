---
name: ngs-evidence-layer
description: Builds a deterministic evidence block for a myeloid NGS case or writes an NGS report from an existing block.md. Use for evidence-block generation or NGS report writing.
---
# NGS evidence layer
## Purpose

Perform the task explicitly requested by the user:

- `evidence-block` — build `<work-dir>/block.md` from one supplied case and the released evidence corpus.
- `ngs-report` — build `<work-dir>/report.md` from the supplied case and an existing `block.md`.
- both — complete evidence-block mode first, then run Step 6 in a fresh bounded model session.

Do not infer the mode from available files.

The skill does not create, edit, audit, or incorporate evidence cards.

## Workflow modes

### Evidence-block mode

1. Step 1 — model: structure the case into `case-input.json`.
2. Step 2 — deterministic: retrieve diagnosis evidence into `step2.json`.
3. Step 3 — model: adjudicate the diagnosis and obtain mandatory user review.
4. Step 4 — deterministic: retrieve the full evidence bundle into `bundle.json`.
5. Step 5 — deterministic: render `block.md`.

Step 4 is blocked until Step 3 user review is complete and the user issues the exact continuation word `PROCEED_TO_STEP_4`.

### NGS-report mode

Step 6 only: write `<work-dir>/report.md` in a fresh bounded model session.

## Mandatory file-access policy

File access is **deny by default**.

- Select the operating mode before reading case-specific inputs.
- In each model step, read only its declared model-readable inputs.
- Do not list or search directories or inspect undeclared files.
- Do not supplement inputs with live sources, external tools, or model knowledge.
- Do not carry information between bounded model steps unless supplied as an allowed input.
- Deterministic commands may read what their command requires; this does not make those files model-readable.
- Run only the commands declared below and write only the declared outputs.
- Do not modify an output written by a deterministic command.
- If a required input is missing, unreadable, malformed, or inconsistent with its contract, stop and report the error. Do not infer or replace it.

Step 3 may present its diagnosis argument and `adjudication.json` in chat. Steps 3 and 6 use fresh bounded model sessions.

## Working directory

Before Step 1:

- If the user supplies a directory, use it.
- Otherwise, run exactly:

  ```bash
  python scripts/create_work_dir.py
  ```

  Treat its single output line as `<work-dir>`. Do not substitute another directory.

- Resolve a user-supplied directory to an absolute path and create it if necessary.
- Fail if it is not a directory or is unreadable or unwritable. Do not fall back to another directory.
- Print:

  ```text
  Working directory: <absolute-path>
  ```

- Retain the directory after success or failure. Do not clean it up automatically.

For report-only mode, the user must supply or identify a working directory containing `block.md`. Do not search for one.

## Missing and unreported results

- Treat a reported test result as complete unless explicitly described as partial, selected, limited, abbreviated, pending, or otherwise incomplete.
- In a complete test, an unlisted abnormal finding is negative only within that test's scope.
- Do not assume that an unmentioned test was performed.
- A negative sequencing result does not exclude copy-number changes, rearrangements, or other findings unless the test assessed them.
- If cytogenetic results are not supplied, assume normal conventional cytogenetics for interpretation and record this in Step 1 as a `workflow_assumption`, not a patient result.
- Do not state that cytogenetics were performed or that a specific cytogenetic abnormality was formally excluded.
- Do not use the normal-cytogenetics assumption when supplied karyotype, FISH, copy-number, or other findings conflict with it.

## Step 1 — Structure the case

### Model-readable inputs

Read only:

- the one case document supplied by the user;
- `schema/disease_vocabulary.json`.

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
  - Apply **Missing and unreported results**.
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

Use a fresh bounded model session.

### Model-readable inputs

Read only:

- `prompts/diagnostic_adjudication_prompt.md`;
- `<work-dir>/step2.json`.

### Required action

Follow `prompts/diagnostic_adjudication_prompt.md` exactly, using `step2.json` as the complete patient-fact and diagnosis-evidence boundary.

If `diagnosis_cards` is empty:

- do not reclassify;
- set `status` to `"indeterminate"`;
- preserve `provisional_disease` as both `refined_disease` and `downstream_filter_disease`;
- set `diagnostic_label` to null;
- set `driven_by` and `criterion_assessment` to `[]`;
- state in `reason` that no corpus diagnosis evidence was retrieved;
- continue to mandatory user review.

### Mandatory user review

1. Write the initial `<work-dir>/adjudication.json` with `user_review.decision: "pending"` as required by the adjudication prompt.
2. Present:
   - the proposed integrated diagnosis;
   - one concise evidence-bounded paragraph defending it, or a short list if there are several distinct reasons.
3. Ask the user to agree or disagree.
4. Update `user_review`:
   - **agree:** set `decision` to `"agree"` and copy the model's `diagnostic_label` and `refined_disease` exactly;
   - **disagree:** require a revised diagnostic label and one exact downstream category from `allowed_refined_diseases`, then set `decision` to `"disagree"`.
5. Do not alter the model's original top-level adjudication fields after user review.
6. Set `downstream_filter_disease` to `user_review.refined_disease`.
7. Present the complete updated `adjudication.json` and ask the user to reply with the exact word `PROCEED_TO_STEP_4`.

Do not begin Step 4 in the response that presents the updated JSON. Any other response leaves Step 4 blocked.

### Output

Write only `<work-dir>/adjudication.json`, using the exact output shape required by `prompts/diagnostic_adjudication_prompt.md`.

Before Step 4, `user_review.decision` must be `"agree"` or `"disagree"` with the corresponding reviewed diagnosis. Do not create a separate review, approval, or override file.

## Step 4 — Retrieve the full evidence bundle

### Entry

All must be true:

- `adjudication.json` records `user_review.decision` as `"agree"` or `"disagree"`;
- the complete updated `adjudication.json` was presented to the user;
- the user subsequently replied exactly `PROCEED_TO_STEP_4`.

Do not accept similar wording or a continuation word given before the updated JSON was presented.

### Command

Run exactly:

```bash
python scripts/retrieve.py full \
  --diagnosis-result <work-dir>/step2.json \
  --adjudication-result <work-dir>/adjudication.json \
  --output <work-dir>/bundle.json
```

### Exit

- The command succeeds.
- `<work-dir>/bundle.json` exists.

Do not read or modify `bundle.json` in this step.

## Step 5 — Render the evidence block

### Entry

Step 4 succeeded and `<work-dir>/bundle.json` exists.

### Command

Run exactly:

```bash
python scripts/render.py \
  --bundle <work-dir>/bundle.json \
  --output <work-dir>/block.md
```

### Exit

- The command succeeds.
- `<work-dir>/block.md` exists.

Do not read or modify `block.md` in this step.

## Step 6 — Write the NGS report

Run only when explicitly requested, using a fresh bounded model session.

### Model-readable inputs

Read only:

- the original case document supplied by the user;
- `<work-dir>/block.md`;
- `rules/agreed_reporting_rules`.

If any required input is missing, unreadable, or malformed, stop and report the error.

### Source hierarchy

- **Case:** patient identity, specimen information, clinical context, test results, variants, measurements, and other patient-specific facts only.
- **`block.md`:** exclusive source for diagnosis, classification, prognosis, treatment, biomarkers, germline interpretation, literature claims, and references.
- **Reporting rules:** selection, structure, and wording only; they do not establish patient facts or clinical assertions.
- Do not strengthen, reconcile, or resolve interpretations beyond `block.md`.
- Preserve material uncertainty, disagreement, limitations, and qualifiers.
- Do not treat an interpretation stated only in the case as evidence unless `block.md` independently supports it.
- Do not copy workflow metadata into the clinical report unless the reporting rules require it.
- If the case and `block.md` conflict, do not silently repair the inconsistency.

### Required action

Write a complete NGS report following `rules/agreed_reporting_rules` and the source hierarchy above.

- Include only supplied patient findings.
- Include only interpretations and references supported by `block.md`.
- Retain clinically material qualifications and uncertainty.
- Handle unsupported sections as directed by the reporting rules.

### Output

Write exactly one file:

`<work-dir>/report.md`

The file must contain the report only. Do not include process commentary, source-audit notes, confidence commentary, alternative drafts, or an additional summary.

## Final delivery contract

Deliver only the artifact or artifacts explicitly requested by the user.

### Evidence-block mode

Return `<work-dir>/block.md` unchanged.

### NGS-report mode

Return `<work-dir>/report.md`.

Do not also return `block.md` unless explicitly requested.

### Both outputs explicitly requested

Return separately:

1. `<work-dir>/block.md`;
2. `<work-dir>/report.md`.

Do not combine them.
