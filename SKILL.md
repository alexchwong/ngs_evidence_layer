---
name: ngs-evidence-layer
description: Builds a deterministic evidence block for a myeloid NGS case, with automatic or manual diagnostic adjudication, or writes an NGS report from a new or completed evidence workflow.
---
# NGS evidence layer
## Purpose

Perform the task explicitly requested by the user:

- `evidence-block` — run Steps 1–5; Step 3 is automatic. Return `<work-dir>/block.md`.
- `evidence-block manual` — run Steps 1–5; Step 3 requires user confirmation. Return `<work-dir>/block.md`.
- `ngs-report` — run Steps 1–6; Step 3 is automatic and Step 6 follows Step 5 without stopping. Return `<work-dir>/report-final.md`.
- `evidence-to-report` — verify Step 5 has already produced `<work-dir>/block.md`, then run Step 6 only. Return `<work-dir>/report-final.md`.

Do not infer the mode from available files.

The skill does not create, edit, audit, or incorporate evidence cards.

## Workflow modes

### Evidence-block mode

`evidence-block` and `evidence-block manual` run:

1. Step 1 — model: write the supplied clinical case to `case.md` and structure it into `case-input.json`.
2. Step 2 — deterministic: retrieve diagnosis evidence into `step2.json`.
3. Step 3 — model: adjudicate the diagnosis and append the integrated diagnosis to `case.md`.
4. Step 4 — deterministic: retrieve the full evidence bundle into `bundle.json`.
5. Step 5 — deterministic: render `block.md`.

For `evidence-block`, Step 3 is automatic and proceeds directly to Step 4.
For `evidence-block manual`, Step 3 requires one user confirmation or revision before Step 4.

### NGS-report mode

- `ngs-report` — run Steps 1–6. Step 3 is automatic. After Step 5 succeeds, start Step 6 immediately.
- `evidence-to-report` — verify `<work-dir>/case.md` and a non-empty `<work-dir>/block.md` exist, skip Steps 1–5, and run Step 6 only.

### Report format

For `ngs-report` and `evidence-to-report`, select the formatting prompt before report generation:

- Default: `prompts/formatting/default.md`.
- If the user explicitly specifies another file from `prompts/formatting/`, use that file.
- Do not list or search `prompts/formatting/` to choose a file.
- Do not use a formatting prompt outside `prompts/formatting/`.
- Retain the selected path as `<format-prompt>` for Step 6.

For `ngs-report`, select `<format-prompt>` before Step 1. For `evidence-to-report`, select it before Step 6.

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

Step 3 may present its diagnosis argument and `adjudication.json` in chat in `evidence-block manual`. Step 3 uses a fresh bounded model session. Step 6 uses two fresh bounded model sessions; Pass 2 receives no information from Pass 1 except `<work-dir>/report-draft.md`.

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

For `evidence-to-report`, the user must supply or identify a working directory containing `case.md` and `block.md`. Do not search for one.

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

First identify the exact user-supplied content that constitutes the clinical case and write it to `<work-dir>/case.md`.

`case.md` must:
- contain only the supplied clinical case, preserving that content verbatim and in its original order;
- include all supplied patient, specimen, morphology, laboratory, cytogenetic, molecular, treatment, and other clinical case information;
- exclude workflow instructions, output requests, and other non-case commentary;
- contain no model interpretation, summary, normalisation, literature information, or added facts.

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

Write `<work-dir>/case.md` as specified above.

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
- state in `reason` that no corpus diagnosis evidence was retrieved.

For `evidence-block` and `ngs-report`:
- set `user_review` to `"automatic"`;
- use the model adjudication as final;
- keep `downstream_filter_disease` equal to `refined_disease`;
- do not ask for user confirmation.

For `evidence-block manual`, complete the manual user review below.

After the final integrated diagnosis is determined, append exactly one sentence to `<work-dir>/case.md`:

`Integrated diagnosis: <diagnosis>, based on <specific reason, 20 words or fewer>. (<Author et al, year>).`

- Use the final integrated diagnostic label; if none exists, use the final major diagnostic category.
- Base the reason only on supplied case facts and retrieved diagnosis cards.
- Use the citation of a supporting diagnosis card.
- If no diagnosis card supports the final integrated diagnosis, use `(no citation required)` instead.
- Do not otherwise modify `case.md`.

### Manual user review

Apply only to `evidence-block manual`.

1. Write the initial `<work-dir>/adjudication.json` with `user_review.decision: "pending"`.
2. Present the proposed integrated diagnosis and one concise evidence-bounded argument, or a short list for several distinct reasons.
3. Ask the user to agree or disagree.
4. Update `user_review`:
   - **agree:** set `decision` to `"agree"` and copy the model's `diagnostic_label` and `refined_disease` exactly;
   - **disagree:** require a revised diagnostic label and one exact downstream category from `allowed_refined_diseases`, then set `decision` to `"disagree"`.
5. Do not alter the model's original top-level adjudication fields after user review.
6. Set `downstream_filter_disease` to `user_review.refined_disease`.
7. Append the required integrated-diagnosis sentence to `case.md` and proceed to Step 4. Do not require a separate continuation word.

### Output

Finalise `<work-dir>/adjudication.json` using the exact output shape allowed by `prompts/diagnostic_adjudication_prompt.md`.

Append exactly one integrated-diagnosis sentence to `<work-dir>/case.md` as specified above. Do not otherwise modify `case.md`.

Before Step 4, `user_review` must be either:
- `"automatic"`; or
- a completed review object with `decision` equal to `"agree"` or `"disagree"`.

Do not create a separate review, approval, diagnosis, or override file.

## Step 4 — Retrieve the full evidence bundle
### Entry

All must be true:

- Step 3 completed;
- `user_review` is `"automatic"` or records `decision` as `"agree"` or `"disagree"`;
- if `user_review` is `"automatic"`, `downstream_filter_disease` equals `refined_disease`;
- if `user_review` is an object, `downstream_filter_disease` equals `user_review.refined_disease`.

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

Run only for `ngs-report` or `evidence-to-report`.

For `ngs-report`, begin Step 6 immediately after Step 5 succeeds. Do not stop for user input.

For `evidence-to-report`, first verify `<work-dir>/case.md` and a non-empty `<work-dir>/block.md` exist. If not, stop and report that Step 5 has not been completed for that working directory. Do not rerun Steps 1–5.

### Pass 1 — Answer the reporting rules

Use a fresh bounded model session.

#### Model-readable inputs

Read only:

- `<work-dir>/case.md`;
- `<work-dir>/block.md`;
- `rules/agreed_reporting_rules.md`.

If any required input is missing, unreadable, or malformed, stop and report the error.

#### Source hierarchy

- **`case.md`:** sole source of truth for patient identity, specimen information, clinical context, test results, variants, measurements, other patient-specific facts, and the final integrated diagnosis.
- Use the `Integrated diagnosis:` sentence in `case.md` as the final diagnosis. Do not re-adjudicate it in Step 6.
- **`block.md`:** exclusive source for literature-derived classification, prognosis, treatment, biomarkers, germline interpretation, clinical associations, and references.
- **Reporting rules:** questions and constraints to apply; they do not establish patient facts or clinical assertions.
- Do not strengthen, reconcile, or resolve interpretations beyond `block.md`.
- Preserve material uncertainty, disagreement, limitations, and qualifiers.
- Do not copy workflow metadata into the report draft unless a reporting rule requires it.
- If `case.md` and `block.md` conflict, do not silently repair the inconsistency.

#### Required action

Answer every numbered rule under R1–R5 in `rules/agreed_reporting_rules.md`.

For each rule:

- identify it by rule number;
- give a 1–3 sentence case-specific answer;
- answer the rule even when it is not applicable or the result is negative;
- end every sentence with one citation marker:
  - one or more supporting citations in parentheses, e.g. `(Smith et al, 2024; Jones et al, 2023)`; or
  - `(no citation required)`;
- use only literature citations supported by `block.md`;
- use `(no citation required)` only when the sentence does not require literature support.

Do not omit a rule because it is unlikely to appear in the final report.

#### Output

Write only:

`<work-dir>/report-draft.md`

### Pass 2 — Format the final report

Use a fresh bounded model session.

#### Model-readable inputs

Read only:

- `<format-prompt>`;
- `<work-dir>/report-draft.md`.

Do not read `case.md`, `block.md`, `rules/agreed_reporting_rules.md`, the original case document, or any other file. Do not use information carried from Pass 1 except `report-draft.md`.

If either required input is missing, unreadable, or malformed, stop and report the error.

#### Required action

Follow `<format-prompt>` exactly, using `report-draft.md` as the sole source of report content.

Do not introduce a clinical assertion, qualification, citation, or patient fact that is absent from `report-draft.md`.

#### Output

Write only:

`<work-dir>/report-final.md`

The file must contain the final report only. Do not include process commentary, rule numbers, source-audit notes, confidence commentary, alternative drafts, or an additional summary.

## Final delivery contract

Deliver only the artifact or artifacts explicitly requested by the user.

### Evidence-block mode

For `evidence-block` and `evidence-block manual`, return `<work-dir>/block.md` unchanged.

### NGS-report mode

For `ngs-report` and `evidence-to-report`, return `<work-dir>/report-final.md`.

Do not also return `block.md` unless explicitly requested.

### Both outputs explicitly requested

Use `ngs-report` and return separately:

1. `<work-dir>/block.md`;
2. `<work-dir>/report-final.md`.

Do not combine them.
