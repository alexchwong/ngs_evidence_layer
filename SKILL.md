---
name: ngs-evidence-layer
description: Builds a deterministic evidence block or NGS report for a myeloid NGS case, supports automatic or manual diagnostic adjudication, and can run repository examples or validation cases.
---
# NGS evidence layer
## Purpose

Perform only the mode explicitly requested by the user:

- `evidence-block` — run Steps 0–5; diagnosis review is automatic (skip 3B). Return `<work-dir>/evidence.md`.
- `evidence-block manual` — run Steps 0–5; Step 3B requires user confirmation or revision. Return `<work-dir>/evidence.md`.
- `ngs-report` — run Steps 0–6; diagnosis review is automatic (skip 3B) and reporting follows Step 5 without stopping. Step 7 renders `<work-dir>/report-final.md` in chat and deterministically packages all full-run workflow artifacts into a separate debug ZIP.
- `evidence-to-report` — run Step 0, verify Step 5 outputs already exist, then run Steps 6A–6C only. Step 7 renders `<work-dir>/report-final.md` in chat.
- `nel-demo example <N>` — resolve one numbered repository example and run the same automatic Steps 0–6 as `ngs-report`; Step 7 displays the case, generated report, and matching expected behaviour. Do not read the expected file before `report-final.md` is complete.
- `nel-validate <case-id>` — retrieve one legacy validation case from `validation/case_summary.md` without its marking criteria, run the same automatic Steps 0–6 as `ngs-report`, then in Step 7 deterministically package both an external-marking ZIP and a separate full-run debug ZIP. No marking model runs in the report-generation session.
- `nel-validate-function <case-id>` — retrieve one function-targeted validation case from `validation/case_functional.md` without its marking criteria, run the same automatic Steps 0–6 as `ngs-report`, then package `nel-validation-function-<case-id>.zip` plus the separate debug ZIP. `validation/case_functional_manifest.md` is evaluator/developer-only and is never a model input.

Do not infer the mode from available files. The skill does not create, edit, audit, or incorporate evidence cards.

## Workflow

- Step 0 — deterministic/setup: establish workflow state and `<work-dir>`; record `<format-prompt>` when needed.
- Step 1A — model via `prompts/workflow/capture_case.md`: capture the supplied clinical case verbatim in `case.md`.
- Step 1B — model with deterministic setup via `prompts/workflow/structure_case.md`: deterministically expose only the small case-major-category list, then model-author `case-input.json` from `case.md` and that list.
- Step 2 — deterministic: broadly retrieve diagnosis evidence by case-major category or case gene into `diagnostic_evidence.md`, exposing only six-character runtime card tags while retaining stable IDs privately.
- Step 3A — model via `prompts/workflow/adjudicate_diagnosis.md`: adjudicate the diagnosis into `adjudication.json`.
- Step 3B — model/user: manual review only; agreement is a direct copy, while a revision is re-grounded via `prompts/workflow/revise_diagnosis.md`.
- Step 3C — deterministic: validate the completed adjudication and append its effective integrated diagnosis to `case.md`.
- Steps 3D–5 — deterministic: retrieve the full evidence bundle into `bundle.json`, then render the single model-facing `evidence.md` using short opaque runtime card tags plus a private `card-tags.json` deconvolution map.
- Step 6A — model via `prompts/workflow/analyse_report.md` + shared `prompts/workflow/citation_rules.md` + deterministic validation: classify every reporting-rule answer as `REPORT:` or `OMIT:` in strict `report-draft.md` Markdown with a compulsory terminal citation disposition on every line.
- Step 6B — model via `prompts/workflow/format_report.md` + shared `prompts/workflow/citation_rules.md` plus `<format-prompt>` + deterministic validation: render only `REPORT:` content from `report-draft.md` into `report-final.md`, preserving exact runtime card-tag markers, then validate them.
- Step 6C — deterministic: deconvolve card tags, replace markers with Vancouver-style citations, and render the bibliography.
- Step 7 — post-report delivery and deterministic packaging; full `ngs-report`-equivalent runs get a debug ZIP containing every workflow artifact, while `nel-validate` and `nel-validate-function` additionally get separate external-marking ZIPs containing only the report, selected validation case, and self-contained marking prompt.

`evidence-to-report` skips Steps 1A–5 after Step 0 verifies `<work-dir>/case.md`,
`<work-dir>/evidence.md` and `<work-dir>/card-tags.json` exist. Do not
rerun skipped steps.


## Workflow state

The workflow may define these global variables:

- `<mode>` — the explicit operating mode selected in Step 0;
- `<work-dir>` — the fixed working directory;
- `<format-prompt>` — the selected file under `prompts/formatting/` when reporting is requested;
- `<demo-case>` and `<demo-expected>` — resolved demo paths for `nel-demo`;
- `<validation-case>` — the requested validation case identifier for `nel-validate` or `nel-validate-function`.

Paths may be recorded without permission to read their contents. Model-readable access is controlled only by the declarations in each step.


## Mandatory file-access policy

File access is **deny by default**.

- In each model step, read only its declared model-readable inputs.
- A path may be selected or recorded without permission to read its contents.
- Do not list or search directories or inspect undeclared files.
- Do not supplement inputs with live sources, external tools, or model knowledge.
- Do not carry information between bounded model steps unless supplied as an allowed input.
- Deterministic commands may read what their command requires; this does not make those files model-readable.
- Treat declared deterministic commands as opaque operations: do not open, read, search, grep, or otherwise inspect their Python source unless that source is explicitly declared as a model-readable input.
- Run only the commands declared below and write only the declared outputs. Do not search for or substitute another script or command to perform a model task.
- If a step says the model writes an output, the model must generate that output only from the declared model-readable inputs; do not look for repository code that could generate it instead.
- Do not modify an output written by a deterministic command.
- If a required input is missing, unreadable, malformed, or inconsistent with its contract, stop and report the error. Do not infer or replace it.
- For `nel-validate`, do not model-read `validation/case_summary.md`, `prompts/workflow/mark_validation_report.md`, or marking criteria at any point. Step 7 may read them only through the declared deterministic packaging command.
- For `nel-validate-function`, do not model-read `validation/case_functional.md`, `validation/case_functional_manifest.md`, `prompts/workflow/mark_validation_report.md`, or marking criteria at any point. `case_functional_manifest.md` is never a runtime model input. Step 7 may read `case_functional.md` only through the declared deterministic packaging command.


## Model-task policy

For every model step:

1. Use a fresh bounded model session unless the step explicitly says otherwise.
2. Read only the task prompt and additional model-readable inputs declared by that step.
3. Follow shared rules in this `SKILL.md` and task-specific instructions in the workflow prompt.
4. Write only the declared output.
5. Do not carry information from an earlier bounded model step unless it is present in an allowed input.

`SKILL.md` controls workflow state, file access, shared invariants, commands, branching, validation loops, and delivery. `prompts/workflow/*.md` controls only the model task performed inside those boundaries. If a task prompt conflicts with a workflow or access rule in `SKILL.md`, `SKILL.md` prevails.

## Shared patient-result semantics

These rules apply only to Step 1B case structuring, Step 3A diagnostic adjudication, and Step 3B diagnostic revision. Reporting steps must not independently reconstruct missing results from these rules.


- Treat a reported test result as complete unless explicitly described as partial, selected, limited, abbreviated, pending, or otherwise incomplete.
- In a complete test, an unlisted abnormal finding is negative only within that test's scope.
- Do not assume that an unmentioned test was performed.
- A negative sequencing result does not exclude copy-number changes, rearrangements, or other findings unless the test assessed them.
- If cytogenetic results are not supplied, assume normal conventional cytogenetics for interpretation and record this as a `workflow_assumption`, not a patient result.
- Do not state that cytogenetics were performed or that a specific cytogenetic abnormality was formally excluded.
- Do not use the normal-cytogenetics assumption when supplied karyotype, FISH, copy-number, or other findings conflict with it.

## Step 0 — Establish workflow state

### Required action

1. Select the explicit operating mode before reading case-specific inputs.
   - For `nel-demo example <N>`, require one integer `N` from 1 through 6 and run exactly:

     ```bash
     python scripts/resolve_demo.py <N>
     ```

   - Record the command's first output line as `<demo-case>` and second as `<demo-expected>`.
   - Do not read either file in Step 0.
   - For `nel-validate <case-id>` or `nel-validate-function <case-id>`, require one case variant identifier such as `1A` and record it as `<validation-case>`. Do not retrieve the case or read any validation file in Step 0.
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

5. For `ngs-report`, `evidence-to-report`, `nel-demo`, `nel-validate`, and `nel-validate-function`, record `<format-prompt>`:
   - default: `prompts/formatting/default.md`;
   - if the user explicitly specifies another file from `prompts/formatting/`, record that path;
   - do not list or search `prompts/formatting/`;
   - do not use a formatting prompt outside `prompts/formatting/`;
   - **record the path only. Do not read `<format-prompt>` until Step 6B.**
6. For `evidence-to-report`, verify only that `<work-dir>/case.md`,
   `<work-dir>/evidence.md` and `<work-dir>/card-tags.json` exist, and `<work-dir>/evidence.md` is non-empty.
   Do not read their contents in Step 0.
7. Retain `<work-dir>` after success or failure. Do not clean it up automatically.

### Exit

- Operating mode is fixed.
- `<work-dir>` is fixed.
- If reporting is requested, `<format-prompt>` is fixed but unread.
- For `evidence-to-report`, the required Step 5 outputs exist.
- For `nel-demo`, `<demo-case>` and `<demo-expected>` are fixed but unread.
- For `nel-validate` and `nel-validate-function`, `<validation-case>` is fixed and validation files remain unread.

## Step 1A — Capture the case

Run only when Steps 1–5 are required.

For `nel-validate`, run exactly:

```bash
python validation/retrieve_cli.py case <validation-case> > <work-dir>/case.md
```

The command must succeed. Do not model-read `validation/case_summary.md` or any marking criteria. Proceed directly to Step 1B.

For `nel-validate-function`, run exactly:

```bash
python validation/retrieve_cli.py case <validation-case> \
  --file validation/case_functional.md > <work-dir>/case.md
```

The command must succeed. Do not model-read `validation/case_functional.md`, `validation/case_functional_manifest.md`, or any marking criteria. Proceed directly to Step 1B.

For all other modes, use a fresh bounded model session.

### Model-readable inputs

Read only:

- `prompts/workflow/capture_case.md`;
- the one designated case source:
  - normal modes: the one user-designated case source;
  - `nel-demo`: `<demo-case>`.

Do not read any other repository file in model Step 1A. In `nel-demo`, `<demo-case>` is the sole permitted repository-file exception apart from the declared workflow prompt.

### Required action

Follow `prompts/workflow/capture_case.md` exactly and write only `<work-dir>/case.md`.

### Output

`<work-dir>/case.md`.

## Step 1B — Structure the case

This is a **model-authored step with deterministic setup**. The Python command below creates only the allowed category list; it does not create `case-input.json`. Do not inspect the script or search for another script to structure the case.

### Deterministic setup

Run exactly:

```bash
python scripts/case_major_categories.py --output <work-dir>/case-major-categories.json
```

Treat this command as opaque. After it succeeds, use a fresh bounded model session for the model task below.

### Model-readable inputs

Read only:

- `prompts/workflow/structure_case.md`;
- `<work-dir>/case.md`;
- `<work-dir>/case-major-categories.json`.

Do not reread the original case source.

### Model task

The model, not a Python script, must author `<work-dir>/case-input.json`. Follow `prompts/workflow/structure_case.md` exactly and write JSON only to `<work-dir>/case-input.json` using only the declared model-readable inputs above.

### Output

`<work-dir>/case-input.json`.

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
- `<work-dir>/diagnostic_evidence.md` exists.
- Diagnosis retrieval includes cards belonging to `case_major_category`, existing direct diagnosis `retrieval_related` scope, or a reported case gene.
- `provisional_disease` remains the supplied free-text starting diagnosis.
- `allowed_refined_diseases` is limited to canonical diseases represented by retrieved diagnosis cards plus the selected major category fallback; it is not the full disease vocabulary.

Do not read or modify `diagnostic_evidence.md` in this step.

## Step 3 — Adjudicate the diagnosis

### Step 3A — Model adjudication

Use a fresh bounded model session.

#### Model-readable inputs

Read only:

- `prompts/workflow/adjudicate_diagnosis.md`;
- `<work-dir>/diagnostic_evidence.md`.

#### Required action

Follow `prompts/workflow/adjudicate_diagnosis.md` exactly, using `diagnostic_evidence.md` as the complete patient-fact and diagnosis-evidence boundary.

For `evidence-block`, `ngs-report`, `nel-demo`, `nel-validate`, and `nel-validate-function`:
- set `user_review` to `"automatic"`;
- keep `downstream_filter_disease` equal to `refined_disease`;
- do not ask for user confirmation;
- proceed directly to deterministic Step 3C.

For `evidence-block manual`:
- write the initial `<work-dir>/adjudication.json` with `user_review.decision: "pending"` and the exact pending review fields required by the adjudication prompt;
- keep the initial `downstream_filter_disease` equal to the model's `refined_disease`;
- proceed to Step 3B.

#### Output

Write only `<work-dir>/adjudication.json`.
Use runtime card tags exactly as shown in `diagnostic_evidence.md`; do not emit or reconstruct stable card IDs. Step 3C deterministically deconvolves valid tags to private stable IDs before downstream use.

### Step 3B — Manual user review

Run only for `evidence-block manual`.

First read only `<work-dir>/adjudication.json`, present the proposed integrated diagnosis and concise model reason, and ask the user to agree or provide a revised diagnostic label and downstream category.

#### If the user agrees

Update only `user_review` and `downstream_filter_disease`:

- `decision`: `"agree"`;
- copy top-level `diagnostic_label` to `user_review.diagnostic_label`;
- copy top-level `refined_disease` to `user_review.refined_disease`;
- copy top-level `reason` to `user_review.reason`;
- copy top-level `driven_by` to `user_review.card_tags`;
- set `downstream_filter_disease` to `user_review.refined_disease`.

Do not start another model adjudication.

#### If the user revises the diagnosis

Use a fresh bounded model session and read only:

- `prompts/workflow/revise_diagnosis.md`;
- `<work-dir>/diagnostic_evidence.md`;
- `<work-dir>/adjudication.json`;
- the user's revised diagnostic label and downstream category.

Follow `prompts/workflow/revise_diagnosis.md` exactly.

If the requested revision is supportable, replace `<work-dir>/adjudication.json` only with the complete updated JSON returned by that task.

If the requested revision cannot be grounded in retrieved diagnosis evidence, do not alter `<work-dir>/adjudication.json`; explain that Step 3C remains blocked until the user supplies a supportable revision or agrees with the model adjudication.

### Step 3C — Deterministically append the integrated diagnosis

This step is compulsory after automatic adjudication or completed manual review. It is not a model step.

Run exactly:

```bash
python scripts/append_integrated_diagnosis.py \
  --case <work-dir>/case.md \
  --diagnosis-result <work-dir>/diagnostic_evidence.md \
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
- `<work-dir>/bundle.json`, `<work-dir>/evidence.md`, and `<work-dir>/card-tags.json` exist.
- `retrieved` retains only diagnosis cards actually cited by Step 3 plus normal full-retrieval cards; separately, `diagnostic_context` carries every Step-2 diagnosis card so `evidence.md` remains complete for a fresh model session.
- Both `diagnostic_evidence.md` and `evidence.md` expose only the same deterministic six-character runtime `card_tag` for a given card, never the stable full `card_id`.
- `card-tags.json` is the deterministic private tag-to-card-ID map for cards rendered in `evidence.md` and is not model-readable. The private Step-2 JSON retains the eligibility-universe tag table needed for deterministic Step-3 deconvolution.

Do not model-read or modify `diagnostic_evidence.md`, `adjudication.json`, `bundle.json`, `evidence.md`, or `card-tags.json` in Steps 3D–5.

## Step 6 — Write the NGS report

Run only for `ngs-report`, `evidence-to-report`, `nel-demo`, `nel-validate`, or `nel-validate-function`.

For `ngs-report`, `nel-demo`, `nel-validate`, and `nel-validate-function`, begin Step 6A immediately after Step 5 succeeds. Do not stop for user input.

For `evidence-to-report`, Step 0 already verified `<work-dir>/case.md`, `<work-dir>/evidence.md` and `<work-dir>/card-tags.json`; do not rerun Steps 1A–5.

### Step 6A — Answer reporting rules and assign evidence cards

Use one fresh bounded model session.

#### Patient-level conclusion and qualifier style

For each reporting rule, state the **clinically reportable conclusion first**, then add any **material qualifier, condition, exception, or limitation** needed to interpret that conclusion correctly.

- Lead with the positive patient-level fact or classification supported by the case and evidence.
- Do not replace a supported conclusion with an evidence-sufficiency disclaimer merely because the conclusion depends on combining multiple findings or criteria.
- Where a conclusion is conditional, express it in normal clinical-reporting form: **“X is associated with/supports Y, provided that Z.”**
- Qualifiers should identify the circumstances that would modify, override, or limit the stated conclusion.
- Apply the retrieved evidence to the patient facts. A complete patient-level conclusion does not need to appear verbatim in a single evidence item if it follows from the supplied facts and the retrieved criteria.
- If the available information genuinely prevents the conclusion from being assigned, state what can be concluded first, then identify the specific unresolved condition preventing further classification.
- Avoid pipeline or evidence-process language such as “the retrieved evidence does not provide…” in reportable prose. Write the clinical interpretation instead.

Read only:

- `prompts/workflow/analyse_report.md`;
- `prompts/workflow/citation_rules.md`;
- `<work-dir>/case.md`;
- `<work-dir>/evidence.md`;
- `rules/agreed_reporting_rules.md`.

Follow `prompts/workflow/analyse_report.md` exactly and write only `<work-dir>/report-draft.md`.

Run exactly:

```bash
python scripts/report_audit.py validate \
  --draft <work-dir>/report-draft.md \
  --evidence <work-dir>/evidence.md
```

The command is read-only and validates the complete rule sequence, compulsory `REPORT:`/`OMIT:` classification, obvious report-construction meta-language after `REPORT:`, compulsory terminal citation disposition, exact runtime card-tag syntax, duplicate tags, and tag membership in `evidence.md`.

If validation fails for a citation-tag reason (unknown, malformed, misplaced, or duplicated tag), enter **citation-repair mode** until validation succeeds:

- use the validator error to identify the affected rule(s);
- inspect/edit `report-draft.md`;
- re-read `prompts/workflow/citation_rules.md` before repairing the citation defect;
- `evidence.md` is the **only evidentiary/source-content file you may read or re-read** to repair the affected answer or its citation tags;
- find the supporting evidence in `evidence.md` and copy the exact runtime `card_tag` shown there;
- do **not** read or re-read `case.md`, `rules/agreed_reporting_rules.md`, `card-tags.json`, `bundle.json`, `diagnostic_evidence.md`, `adjudication.json`, `cards/`, the corpus/index, the original case document, or any other source file;
- never use `card-tags.json` to recover, translate, verify, or substitute a tag.

For non-citation structural or classification validation failures, correct only the reported rule(s) and defect(s), using the validator message and `prompts/workflow/analyse_report.md`; do not reopen case or evidence sources unless the failure is specifically a citation-tag repair permitted above. Unknown tags are reported with the affected rule IDs.

### Step 6B — Format the final report

Use a fresh bounded model session.

#### Model-readable inputs before `report-final.md` is complete

Read only:

- `prompts/workflow/format_report.md`;
- `prompts/workflow/citation_rules.md`;
- `<format-prompt>`;
- `<work-dir>/report-draft.md`.

Do not read `case.md`, `evidence.md`, `card-tags.json`, `rules/agreed_reporting_rules.md`, the original case document, or any other file. Do not use information carried from Step 6A except `report-draft.md`.

If any required input is missing, unreadable, or malformed, stop and report the error.

#### Required action

Follow `prompts/workflow/format_report.md` exactly. Apply `<format-prompt>` only for report style, ordering, emphasis, compression, and optional-content choices within the mandatory workflow constraints. Use `report-draft.md` as the sole source of report content.

**Step 6B citation invariant:** citation preservation takes precedence over formatting, compression, and word-count targets. A retained or merged assertion must retain the complete citation disposition of its supporting draft content; merged assertions must retain the union of all supporting card markers. In model-written Step 6A and Step 6B Markdown, the citation disposition MUST follow the sentence-ending full stop: `Sentence. [card:abcdef]`, `Sentence. [card:abcdef][card:123456]`, or `Sentence. (no citation required)`. The required order is sentence → full stop → one space → citation disposition; never place a runtime citation marker before the full stop.

#### Output

Write only `<work-dir>/report-final.md`.

Then run exactly:

```bash
python scripts/report_citations.py validate \
  --report <work-dir>/report-final.md \
  --evidence <work-dir>/evidence.md \
  --card-tags <work-dir>/card-tags.json \
  --require-citation-after-full-stop
```

The command is read-only and must succeed before Step 6C. In Step 6B mode it requires every sentence-ending full stop to be followed by one space and either one or more exact runtime card-tag markers or `(no citation required)`. A placement failure reports the affected line and the exact expected syntax, so do not read the validation script to troubleshoot it. This does not rewrite `report-final.md`. If validation fails, use only the validator error, `prompts/workflow/format_report.md`, `prompts/workflow/citation_rules.md`, `<format-prompt>`, and `report-draft.md` to correct `report-final.md`, then rerun it.

### Step 6C — Render citations and references

Run exactly:

```bash
python scripts/report_citations.py render \
  --report <work-dir>/report-final.md \
  --evidence <work-dir>/evidence.md \
  --card-tags <work-dir>/card-tags.json
```

The command validates the model-facing `Sentence. [card:abcdef]` placement, then deterministically moves cited markers before the full stop for the rendered report, resolves each runtime tag through `evidence.md` to its primary publication, replaces card markers with Vancouver-style numeric square-bracket citations, merges adjacent citations, deduplicates publications, removes `(no citation required)`, and appends the cited bibliography. Thus `Sentence. [card:abcdef]` is rendered deterministically as `Sentence [1].`. Do not otherwise modify `report-final.md` after this command.

## Step 7 — Post-report delivery and validation

Run after Step 6C has completed `report-final.md`.

### Step 7A — Package full-run debug artifacts

For `ngs-report`, `nel-demo`, `nel-validate`, and `nel-validate-function`, run exactly:

```bash
python scripts/package_run.py \
  --work-dir <work-dir> \
  --output <work-dir>/ngs-report-debug.zip
```

The command must succeed. It deterministically packages exactly the files generated by the full `ngs-report` workflow:

- `case.md`;
- `case-major-categories.json`;
- `case-input.json`;
- `diagnostic_evidence.md`;
- `adjudication.json`;
- `bundle.json`;
- `evidence.md`;
- `card-tags.json`;
- `report-draft.md`;
- `report-final.md`.

Do not archive the work directory recursively. The explicit allowlist prevents unrelated pre-existing files in a user-supplied work directory from being included. ZIP files are not included inside the debug ZIP.

Do not run this step for `evidence-to-report`, because that mode does not generate the full set of upstream artifacts in the current invocation.

### Step 7B — Mode-specific delivery

- For `ngs-report`, display `<work-dir>/report-final.md` in chat unchanged and return `<work-dir>/ngs-report-debug.zip` as the debugging artifact.
- For `evidence-to-report`, display `<work-dir>/report-final.md` in chat unchanged without another model session.
- For `nel-demo`, only now read `<demo-case>` and `<demo-expected>`; this is the first point permitted to read `<demo-expected>`. Display the case, `<work-dir>/report-final.md`, and expected behaviour unchanged. Also return `<work-dir>/ngs-report-debug.zip`. Do not use `<demo-expected>` to alter any workflow artifact.
- For `nel-validate`, do **not** start another model session and do not model-read marking criteria or the marking prompt. Run exactly:

  ```bash
  python validation/package_marking.py <validation-case> \
    --report <work-dir>/report-final.md \
    --output <work-dir>/nel-validation-<validation-case>.zip
  ```

  The command must succeed. It deterministically creates a separate external-marking ZIP containing exactly:
  - `marking-prompt.md` — `prompts/workflow/mark_validation_report.md` with the validation case identifier and case-specific marking criteria embedded;
  - `validation-case.md` — the original validation case content;
  - `report-final.md` — the completed candidate report.

  `evidence.md`, `card-tags.json`, `bundle.json`, and other generation artefacts must not be included in the **marking** ZIP. They are available only in the separate `<work-dir>/ngs-report-debug.zip`. The external marking model receives only the three marking-bundle files.
- For `nel-validate-function`, do **not** start another model session and do not model-read `validation/case_functional.md`, `validation/case_functional_manifest.md`, marking criteria, or the marking prompt. Run exactly:

  ```bash
  python validation/package_marking.py <validation-case> \
    --case-file validation/case_functional.md \
    --report <work-dir>/report-final.md \
    --output <work-dir>/nel-validation-function-<validation-case>.zip
  ```

  The command must succeed. It deterministically creates a separate external-marking ZIP containing exactly:
  - `marking-prompt.md` — `prompts/workflow/mark_validation_report.md` with the functional validation case identifier and case-specific marking criteria embedded from `validation/case_functional.md`;
  - `validation-case.md` — the original functional validation case content;
  - `report-final.md` — the completed candidate report.

  `validation/case_functional_manifest.md` must not be read or packaged by this workflow. `evidence.md`, `card-tags.json`, `bundle.json`, and other generation artefacts must not be included in the **marking** ZIP. They are available only in the separate `<work-dir>/ngs-report-debug.zip`.

## Final delivery contract

Deliver only the artifact or artifacts explicitly requested by the user.

### Evidence-block mode

For `evidence-block` and `evidence-block manual`, return `<work-dir>/evidence.md` unchanged.

### NGS-report mode

For `ngs-report`, Step 7 renders `<work-dir>/report-final.md` in chat unchanged and also returns `<work-dir>/ngs-report-debug.zip`.

For `evidence-to-report`, Step 7 renders `<work-dir>/report-final.md` in chat unchanged; no full-run debug ZIP is created because upstream artifacts were not generated in that invocation.

Do not also return `evidence.md` separately unless explicitly requested and do not perform an additional rendering pass after Step 7.

### Demo mode

For `nel-demo`, Step 7 performs final delivery by rendering the case, `<work-dir>/report-final.md`, and expected behaviour, and also returns `<work-dir>/ngs-report-debug.zip`. Do not read or render `<demo-expected>` before `report-final.md` is complete and do not perform an additional rendering pass after Step 7.

Do not return `evidence.md` separately unless explicitly requested.

### Validation mode

For `nel-validate`, Step 7 returns two separate artifacts: `<work-dir>/nel-validation-<validation-case>.zip` for external marking and `<work-dir>/ngs-report-debug.zip` for debugging. Do not run a marking model in the same session. Do not model-read the embedded marking criteria or marking prompt.

For `nel-validate-function`, Step 7 returns two separate artifacts: `<work-dir>/nel-validation-function-<validation-case>.zip` for external marking and `<work-dir>/ngs-report-debug.zip` for debugging. Do not run a marking model in the same session. Do not model-read `validation/case_functional_manifest.md`, the embedded marking criteria, or the marking prompt.

Do not additionally return `evidence.md` separately unless explicitly requested.

### Both outputs explicitly requested

Use `ngs-report` and return separately:

1. `<work-dir>/evidence.md`;
2. `<work-dir>/report-final.md`.

Do not combine them.
