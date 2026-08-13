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
- `evidence-to-report` — run Step 0, verify Step 5 outputs already exist, then run Steps 6A–6C only. Step 7 renders `<work-dir>/report-final.md` in chat.
- `nel-demo example <N>` — resolve one numbered repository example and run the same automatic Steps 0–6 as `ngs-report`; Step 7 displays the case, generated report, and matching expected behaviour. Do not read the expected file before `report-final.md` is complete.
- `nel-validate <case-id>` — retrieve one validation case without its marking criteria, run the same automatic Steps 0–6 as `ngs-report`, then in Step 7 retrieve the criteria and mark `report-final.md`.

Do not infer the mode from available files. The skill does not create, edit, audit, or incorporate evidence cards.

## Workflow

- Step 0 — deterministic/setup: establish workflow state and `<work-dir>`; record `<format-prompt>` when needed.
- Step 1A — model: capture the supplied clinical case verbatim in `case.md`.
- Step 1B — deterministic/model: expose only the small case-major-category list, then structure `case.md` into `case-input.json`.
- Step 2 — deterministic: broadly retrieve diagnosis evidence by case-major category or case gene into `step2.json`.
- Step 3A — model: adjudicate the diagnosis into `adjudication.json`.
- Step 3B — model/user: manual review only; agreement is a direct copy, while a revision is re-grounded against `step2.json`.
- Step 3C — deterministic: validate the completed adjudication and append its effective integrated diagnosis to `case.md`.
- Steps 3D–5 — deterministic: retrieve the full evidence bundle into `bundle.json`, render `block.md`, and render card-level `evidence.json` using short opaque runtime card tags plus a private `card-tags.json` deconvolution map.
- Step 6A — model + deterministic validation: answer every reporting rule and attach evidence-card tags in one `report-analysis.json` pass, then render `report-draft.md`.
- Step 6B — model + deterministic validation: format `report-draft.md` into `report-final.md`, preserving exact runtime card-tag markers, then validate them.
- Step 6C — deterministic: deconvolve card tags, replace markers with Vancouver-style citations, and render the bibliography.
- Step 7 — post-report delivery; for `nel-validate`, retrieve evaluator-only inputs and mark `report-final.md`.

`evidence-to-report` skips Steps 1A–5 after Step 0 verifies `<work-dir>/case.md`,
`<work-dir>/evidence.json`, `<work-dir>/card-tags.json`, and a non-empty `<work-dir>/block.md` exist. Do not
rerun skipped steps.


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
   - if the invocation contains the exact modifier `->project`, except for `evidence-to-report`, run exactly:

     ```bash
     python scripts/create_work_dir.py --project
     ```

   - otherwise, except for `evidence-to-report`, run exactly:

     ```bash
     python scripts/create_work_dir.py
     ```

   - Treat the command's single output line as `<work-dir>`. Do not substitute another directory. Do not infer `->project` from natural-language requests.
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
6. For `evidence-to-report`, verify only that `<work-dir>/case.md`,
   `<work-dir>/evidence.json`, and `<work-dir>/card-tags.json` exist and
   `<work-dir>/block.md` exists and is non-empty.
   Do not read their contents in Step 0.
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

First run exactly:

```bash
python scripts/case_major_categories.py --output <work-dir>/case-major-categories.json
```

Then use a fresh bounded model session.

### Model-readable inputs

Read only:

- `<work-dir>/case.md`;
- `<work-dir>/case-major-categories.json`.

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

- `case_major_category`
  - Choose exactly one value from `<work-dir>/case-major-categories.json`.
  - Represent the supplied starting **clinicomorphological major category**, not a molecularly revised diagnosis.
  - Use `no_haematological_malignancy` only when the case specifies no haematological malignancy and the NGS result block contains no variants.
  - Do not use `no_haematological_malignancy` if variants are present.

- `provisional_disease`
  - Preserve the supplied provisional diagnostic wording, including any subtype/entity wording such as `MDS-IB2`.
  - Do not force it to a controlled-vocabulary term and do not revise it using molecular findings.

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
  "case_major_category": "<exact allowed major category>",
  "provisional_disease": "<supplied provisional diagnostic wording>",
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
- Diagnosis retrieval includes cards belonging to `case_major_category`, existing direct diagnosis `retrieval_related` scope, or a reported case gene.
- `provisional_disease` remains the supplied free-text starting diagnosis.
- `allowed_refined_diseases` is limited to canonical diseases represented by retrieved diagnosis cards plus the selected major category fallback; it is not the full disease vocabulary.

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
- set `refined_disease` and `downstream_filter_disease` to `case_major_category`;
- preserve the supplied `provisional_disease` as `diagnostic_label`;
- set `driven_by` and `criterion_assessment` to `[]`;
- state in `reason` that no corpus diagnosis evidence was retrieved.

For `evidence-block`, `ngs-report`, `nel-demo`, and `nel-validate`:
- set `user_review` to `"automatic"`;
- keep `downstream_filter_disease` equal to `refined_disease`;
- do not ask for user confirmation;
- proceed directly to deterministic Step 3C.

For `evidence-block manual`:
- write the initial `<work-dir>/adjudication.json` with `user_review.decision: "pending"` and the exact pending review fields required by the adjudication prompt;
- proceed to Step 3B.

#### Output

Write only `<work-dir>/adjudication.json`.

### Step 3B — Manual user review

Run only for `evidence-block manual`.

First read only `<work-dir>/adjudication.json`, present the proposed integrated diagnosis and concise model reason, and ask the user to agree or provide a revised diagnostic label and downstream category.

#### If the user agrees

Update only `user_review` and `downstream_filter_disease`:

- `decision`: `"agree"`;
- copy top-level `diagnostic_label` to `user_review.diagnostic_label`;
- copy top-level `refined_disease` to `user_review.refined_disease`;
- copy top-level `reason` to `user_review.reason`;
- copy top-level `driven_by` to `user_review.card_ids`;
- set `downstream_filter_disease` to `user_review.refined_disease`.

Do not start another model adjudication.

#### If the user revises the diagnosis

Use a fresh bounded model session and read only:

- `<work-dir>/step2.json`;
- `<work-dir>/adjudication.json`;
- the user's revised diagnostic label and downstream category.

Re-ground the requested revision using only supplied case facts and retrieved diagnosis cards. Do not alter the model's original top-level adjudication fields. Update only:

- `user_review.decision` to `"disagree"`;
- `user_review.diagnostic_label` to the grounded revised label;
- `user_review.refined_disease` to one exact `allowed_refined_diseases` value;
- `user_review.reason` to a concise evidence-bounded reason;
- `user_review.card_ids` to one or more exact supporting diagnosis `card_id` values;
- `downstream_filter_disease` to `user_review.refined_disease`.

If the requested revision cannot be grounded in retrieved diagnosis evidence, do not invent support; explain that Step 4 remains blocked until the user supplies a supportable revision or agrees with the model adjudication.

### Step 3C — Deterministically append the integrated diagnosis

This step is compulsory after automatic adjudication or completed manual review. It is not a model step.

Run exactly:

```bash
python scripts/append_integrated_diagnosis.py \
  --case <work-dir>/case.md \
  --diagnosis-result <work-dir>/step2.json \
  --adjudication-result <work-dir>/adjudication.json
```

The command validates the completed adjudication and appends exactly one line using the effective automatic or user-reviewed diagnosis. Do not otherwise modify `case.md`.

### Steps 3D–5 — Retrieve and render

Run exactly:

```bash
python scripts/run_case.py full --work-dir <work-dir>
```

#### Exit

- The command succeeds. If adjudication validation fails, stop.
- `<work-dir>/bundle.json`, `<work-dir>/block.md`, `<work-dir>/evidence.json`, and `<work-dir>/card-tags.json` exist.
- Only diagnosis cards actually cited by Step 3 are carried into the full reporting bundle; prognosis/treatment/biomarker retrieval remains disease-narrow unless adjudication remains broad/indeterminate.
- `evidence.json` preserves one model-visible record per evidence card but exposes only a six-character runtime `card_tag`, never the stable full `card_id`.
- `card-tags.json` is the deterministic private tag-to-card-ID map and is not model-readable.

Do not model-read or modify `step2.json`, `adjudication.json`, `bundle.json`, `block.md`, `evidence.json`, or `card-tags.json` in Steps 3D–5.

## Step 6 — Write the NGS report

Run only for `ngs-report`, `evidence-to-report`, `nel-demo`, or `nel-validate`.

For `ngs-report`, `nel-demo`, and `nel-validate`, begin Step 6A immediately after Step 5 succeeds. Do not stop for user input.

For `evidence-to-report`, Step 0 already verified `<work-dir>/case.md`, `<work-dir>/evidence.json`, `<work-dir>/card-tags.json`, and a non-empty `<work-dir>/block.md`; do not rerun Steps 1A–5.

### Step 6A — Answer reporting rules and assign evidence cards

Use one fresh bounded model session.

Read only:

- `<work-dir>/case.md`;
- `<work-dir>/evidence.json`;
- `rules/agreed_reporting_rules.md`.

Write `<work-dir>/report-analysis.json` with this shape:

```json
{
  "schema_version": "1.0",
  "answers": [
    {
      "rule_id": "R1.1",
      "text": "Patient-specific conclusion or drafting instruction.",
      "citation_status": "cited",
      "card_tags": ["a1b2c3"]
    }
  ]
}
```

Requirements:

- Include every rule from `R1.1` through `R5.9` exactly once and in source order.
- Give each rule a self-contained, case-specific answer.
- Use the integrated diagnosis in `case.md`; do not re-adjudicate it.
- Use `evidence.json` as the complete literature-evidence boundary.
- Keep card-level evidence granularity: cite the exact runtime `card_tag` of every evidence card that directly supports the answer.
- Use only tags copied exactly from `evidence.json`; never infer, reconstruct, shorten or invent a tag.
- Set `citation_status` to `"cited"` when one or more cards directly support the answer and include those tags.
- Set `citation_status` to `"no_citation_required"` with `card_tags: []` when no literature citation is required. This explicit state is compulsory; an empty tag array alone is not sufficient.
- Use a drafting instruction such as `Omit ...` when a rule has no reportable implication.
- Do not add headings, commentary or fields outside the shown shape.

Run exactly:

```bash
python scripts/report_audit.py render \
  --analysis <work-dir>/report-analysis.json \
  --evidence <work-dir>/evidence.json \
  --output <work-dir>/report-draft.md
```

The command validates every rule, citation state and runtime card tag, then deterministically creates `report-draft.md`. If validation fails, correct `report-analysis.json` using only the validator error and the already-permitted Step 6A inputs until it succeeds. Unknown tags are reported with the affected rule IDs. Do not edit `report-draft.md`.

### Step 6B — Format the final report

Use a fresh bounded model session.

#### Model-readable inputs before `report-final.md` is complete

Read only:

- `<format-prompt>`;
- `<work-dir>/report-draft.md`.

Do not read `case.md`, `evidence.json`, `card-tags.json`, `block.md`, `rules/agreed_reporting_rules.md`, the original case document, or any other file. Do not use information carried from Step 6A except `report-draft.md`.

If either required input is missing, unreadable, or malformed, stop and report the error.

#### Required action

Follow `<format-prompt>` exactly, using `report-draft.md` as the sole source of report content.

Treat explicit drafting instructions in `report-draft.md` as constraints, not report prose. Apply instructions such as `Omit ...`, `Do not state ...`, and `Do not infer ...`, then omit the instruction itself from `report-final.md`.

Do not introduce a clinical assertion, qualification, citation, or patient fact absent from `report-draft.md`.

For every retained statement, copy verbatim every exact `[card:<six-character-tag>]` marker associated with its supporting facts. Keep copied markers attached to those facts. When combining retained draft statements, copy all supporting markers verbatim and adjacently. Do not create, infer, alter, shorten, parse, replace, or renumber a card-tag marker. Retain `(no citation required)` for a retained sentence with that marker. Do not write numeric citations or a `## References` section.

#### Output

Write only `<work-dir>/report-final.md`.

Then run exactly:

```bash
python scripts/report_citations.py validate \
  --report <work-dir>/report-final.md \
  --block <work-dir>/block.md \
  --card-tags <work-dir>/card-tags.json
```

The command is read-only and must succeed before Step 6C. If it fails, use only the validator error, `<format-prompt>`, and `report-draft.md` to correct `report-final.md`, then rerun it.

### Step 6C — Render citations and references

Run exactly:

```bash
python scripts/report_citations.py render \
  --report <work-dir>/report-final.md \
  --block <work-dir>/block.md \
  --card-tags <work-dir>/card-tags.json
```

The command deconvolves each runtime tag to its stable card ID, resolves that card through `block.md` to its primary publication, replaces card markers with Vancouver-style numeric square-bracket citations, merges adjacent citations, deduplicates publications, removes `(no citation required)`, and appends the cited bibliography. Do not otherwise modify `report-final.md` after this command.

## Step 7 — Post-report delivery and validation

Run after Step 6C has completed `report-final.md`.

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
