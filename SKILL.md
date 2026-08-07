---
name: ngs-evidence-layer
description: Produces either a deterministic, citable evidence block for a myeloid NGS case or, when explicitly requested, an NGS report grounded exclusively in an existing evidence block. Evidence-block mode uses model decisions only for case structuring and diagnostic adjudication. Report mode reads only the supplied case, block.md, and agreed reporting rules.
---

# NGS evidence layer
## Purpose

Perform exactly one user-selected task:

1. **Evidence-block mode** — produce a deterministic, citable evidence block from one supplied case and the released evidence corpus.
2. **NGS-report mode** — produce an NGS report from the supplied case and an existing `block.md`.

Do not infer the mode from available files. Determine it from the user's explicit request.

Recognise requests to generate, retrieve, build, or render the evidence block as `evidence-block` mode.
Recognise requests to write, draft, or generate the NGS report as `ngs-report` mode.

If the user explicitly requests both, complete evidence-block mode first, then run Step 6 in a fresh bounded model session.

In evidence-block mode, literature-derived assertions must come from corpus evidence. Patient-specific assertions must come from the supplied case.

In NGS-report mode:
- patient-specific assertions must come from the supplied case;
- all literature-derived, disease-related, prognostic, therapeutic, biomarker, and germline interpretation must come from `block.md`;
- `block.md` is the exclusive evidentiary source of truth;
- `rules/agreed_reporting_rules` controls report selection, structure, wording, and handling of evidence but is not an additional clinical evidence source.

The skill does not create, edit, audit, or incorporate evidence cards.
## Workflow modes
### Evidence-block mode

Evidence-block mode has five steps.

Only two steps require model interpretation:

1. Step 1 — read the supplied case and create `case-input.json`.
2. Step 3 — adjudicate the integrated diagnosis, obtain mandatory user review, and finalise `<work-dir>/adjudication.json`.

Steps 2, 4, and 5 are deterministic. The terminal artifact is `<work-dir>/block.md`.
Step 4 is blocked until Step 3 user review is complete and the user issues the exact continuation word `PROCEED_TO_STEP_4`.
### NGS-report mode

NGS-report mode consists only of optional Step 6.

Step 6 must run in a fresh bounded model session. It reads only:

1. the original case document supplied by the user;
2. `<work-dir>/block.md`;
3. `rules/agreed_reporting_rules`.

Its terminal artifact is `<work-dir>/report.md`.
## Mandatory file-access policy

File access is **deny by default**. After reading this skill, at each step read only
the files listed under that step's **Model-readable inputs**.

Select the operating mode before reading any case-specific input.
- In `evidence-block` mode, follow Steps 1–5 and their file-access boundaries.
- In `ngs-report` mode, skip Steps 1–5 and follow only Step 6.
- When both outputs are explicitly requested, complete Steps 1–5, then discard the earlier model context and run Step 6 as a fresh bounded model session.

Do not carry information from Steps 1 or 3 into Step 6. Step 6 receives the original case document again as an explicitly allowed input.

Do not:
- list or search directories;
- inspect a file merely to check whether it might be useful;
- read a file consumed by a deterministic command unless the current step also lists
  it as model-readable;
- inspect any script, corpus file, index file, source publication, ingestion prompt,
  schema, documentation, example, expected output, test, log, or prior step output
  unless the current step explicitly lists that exact file;
- use live sources, external tools, or model knowledge to supplement an input;
- carry information read in one bounded model step into another model step unless the
  later step receives it in an explicitly allowed input.
A deterministic command may read its declared command inputs. That permission applies
to the command, not to the model. Run only the exact commands declared below.
Each step has one output contract. Do not add commentary, alternate artefacts,
summaries, or convenience copies. The mandatory Step 3 user-review exchange is the
sole exception: present the integrated-diagnosis argument and the current complete
contents of `adjudication.json` in chat, but do not create another file. Do not modify
an output after a deterministic command writes it. If a required input is missing,
unreadable, malformed, or inconsistent with its contract, stop and report that
error. Do not browse for a replacement or infer the missing content.
Use a fresh bounded model session for Step 3 and for Step 6. Each session receives exactly the inputs named by its step.
## Working directory

Before Step 1, select the working directory:

1. If the user supplies a directory, use that directory.
2. Otherwise, create a unique directory using the host platform's secure
   system-temporary-directory facility.

For report-only mode, the user must supply or identify a working directory containing `block.md`. Do not search for one.
Resolve the selected directory to an absolute path. Create it if necessary. Fail if
the path exists but is not a directory, or if it is unreadable or unwritable. Never
silently fall back to another directory after the path has been announced.

Print the absolute resolved directory before reading the case for Step 1:

```text
Working directory: /absolute/path/to/directory
```

Retain the directory after success and after failure. Do not perform automatic
cleanup.
Use the selected directory for case-specific outputs:

- `<work-dir>/case-input.json`
- `<work-dir>/step2.json`
- `<work-dir>/adjudication.json`
- `<work-dir>/bundle.json`
- `<work-dir>/block.md`
- `<work-dir>/report.md`, only when Step 6 is requested
## Missing and unreported results

Treat a reported test result as complete unless the case says that it is partial,
selected, limited, abbreviated, pending, or otherwise incomplete. If an abnormal
finding is not listed in a complete test result, treat it as negative for that test.
Do not assume that an unmentioned test was performed. Keep every inferred negative
within the limits of the reported test. A negative sequencing result does not also
exclude a copy-number change, rearrangement, or other finding unless the case says
that the test assessed it.
If cytogenetic results are not supplied, assume normal conventional cytogenetics for
the interpretation. This is a workflow assumption, not a patient result. Record it as
a `workflow_assumption` fact in Step 1. Do not say that cytogenetics were performed or
that a specific cytogenetic abnormality was formally excluded.

Do not use the normal-cytogenetics assumption if the case reports an abnormal
karyotype, FISH result, copy-number result, or another finding that conflicts with it.
## Step 1 — Structure the case

### Model-readable inputs

Read exactly:

1. the one case document supplied by the user;
2. `schema/disease_vocabulary.json`.

Read nothing else.
### Required action

Extract only information stated in the case:

- `provisional_disease`: the supplied starting major diagnostic category, represented
  by one exact allowed case disease value from the disease vocabulary; do not upgrade
  it from model knowledge. Use `no_haematological_malignancy` only when both are true:
  the case stem does not specify a haematological malignancy and the NGS result block
  contains no variants. If variants are present, do not use this case-only value;
- `genes`: genes with reported variants strictly from the NGS result block, not genes
  mentioned only in the history, differential, assay description, another test, or a
  list of genes tested without a reported variant. If the NGS result contains no
  variants, write an empty array;
- `case_facts`: lossless structured patient facts with unique, stable `fact_id`
  values.
Preserve exact variants, values, units, morphology, blood counts, cytogenetic or FISH
findings, treatment context, assay limitations, and other supplied qualifiers. Do not
normalise a value into a stronger proposition. Do not infer phase, clonal order,
allelic state, germline origin, assay coverage, or an unreported clinical feature.
Apply the rules under **Missing and unreported results**. Record one
`test_result_status` fact for each supplied test result that is treated as complete.
Do not create a separate negative fact for every unlisted gene or abnormality. If
cytogenetic results are not supplied, record the normal-cytogenetics assumption as a
`workflow_assumption`, not as a patient result.
### Output

Write exactly one file, `<work-dir>/case-input.json`, containing JSON only with
exactly these three top-level fields:
```json
{
  "provisional_disease": "myeloid neoplasm, unspecified",
  "genes": ["GENE-A"],
  "case_facts": [
    {"fact_id": "F-GENE-A", "type": "variant", "gene": "GENE-A", "classification": "pathogenic"},
    {"fact_id": "F-NGS-STATUS", "type": "test_result_status", "test": "multigene panel", "complete_reported_findings": true},
    {"fact_id": "A-CYTO", "type": "workflow_assumption", "finding": "normal conventional cytogenetics assumed because cytogenetic results were not supplied"}
  ]
}
```
For a stem with no specified haematological malignancy and no reported NGS variants,
use `"provisional_disease": "no_haematological_malignancy"` and `"genes": []`.
Do not include explanatory prose or additional top-level fields.
## Step 2 — Retrieve diagnosis evidence

### Model-readable inputs

None.

Do not read `case-input.json` merely to construct command arguments; the wrapper and
retrieval script consume it. Do not inspect the retrieval script, corpus, index, or
disease vocabulary.

### Command-only inputs

The deterministic command may consume:

- `scripts/run_case.py`;
- `scripts/retrieve.py`;
- `<work-dir>/case-input.json`;
- `output/corpus/nel.corpus.json`;
- `output/corpus/nel.index.json`.
### Required action

Run exactly:

```bash
python scripts/run_case.py diagnosis --work-dir <work-dir>
```

Do not perform diagnostic selection or interpretation in this step.

### Output

The only output is `<work-dir>/step2.json`, exactly as written by the command. Do not
read, edit, summarize, or supplement it in this step.

## Step 3 — Adjudicate the diagnosis

Use a fresh bounded model session.
### Model-readable inputs

Read exactly:

1. `prompts/diagnostic_adjudication_prompt.md`;
2. `<work-dir>/step2.json`.

Read nothing else. Do not read the original case, `case-input.json`, disease
vocabulary, corpus, index, reporting rules, scripts, examples, or repository
documentation.
### Required action

Follow `prompts/diagnostic_adjudication_prompt.md` exactly. Treat `<work-dir>/step2.json`
as the complete patient-fact and diagnosis-evidence boundary. Do not add a fact, rule,
threshold, exclusion, definition, or qualifier from memory.
Apply the recorded `test_result_status` and `workflow_assumption` facts as directed by
the prompt. Do not make the diagnosis indeterminate only because a card mentions a
competing diagnosis or precedence rule. Consider the competing diagnosis when a
supplied mutation, cytogenetic or FISH finding, copy-number result, morphology, blood
count, or clinical feature suggests that it may be present. Its mention in a card is
not by itself enough to raise it.
### Mandatory user review

First determine the evidence-bounded integrated diagnosis, taking the supplied NGS
results into account, and write the initial `<work-dir>/adjudication.json` with
`user_review.decision` set to `"pending"` and both other `user_review` values set to
null.

Then present to the user:
1. the proposed integrated diagnosis; and
2. one concise paragraph defending it using only the cited diagnosis cards and
   supplied case facts. Use a short list instead when there are several distinct
   reasons.

Ask the user to agree or disagree.
- If the user agrees, set `user_review.decision` to `"agree"` and copy the model's
  `diagnostic_label` and `refined_disease` exactly into `user_review`.
- If the user disagrees, require the user to supply both the revised integrated
  diagnostic label and the downstream major diagnostic category. The category must
  be one exact value from `allowed_refined_diseases`. Record those values in
  `user_review` and set `user_review.decision` to `"disagree"`.
Do not alter the model's original evidence-bounded `refined_disease`,
`diagnostic_label`, `criterion_assessment`, `driven_by`, `reason`, or `status` after
the user responds. These fields preserve the model adjudication. Set
`downstream_filter_disease` to the completed `user_review.refined_disease`.

After updating the file:
1. acknowledge whether the user agreed or supplied a revised diagnosis;
2. confirm that `<work-dir>/adjudication.json` was modified;
3. present the complete updated JSON to the user; and
4. ask the user to review it and reply with the exact word `PROCEED_TO_STEP_4`.

Do not begin Step 4 in the same response. Any other response leaves Step 4 blocked.
The diagnosis decision and the continuation word are separate approvals.
### Output

Write exactly one file, `<work-dir>/adjudication.json`. It must contain JSON only and
exactly the output shape required by `prompts/diagnostic_adjudication_prompt.md`.
The initial file may contain `user_review.decision: "pending"`. Before Step 4, it must
contain a completed decision of `"agree"` or `"disagree"` and the corresponding
reviewed diagnosis. Do not create a separate review, approval, or override file.
## Steps 4 and 5 — Retrieve the full evidence bundle and render the evidence block
### Entry preconditions

Do not proceed unless all of the following are true:

1. `adjudication.json` records `user_review.decision` as `"agree"` or `"disagree"`;
2. the complete updated JSON has been presented to the user; and
3. after reviewing that JSON, the user has issued the exact word
   `PROCEED_TO_STEP_4`.
Do not infer approval from similar wording, an earlier diagnosis decision, or the
presence of a completed `user_review` object. Do not proceed in the same response in
which the updated JSON was presented. The deterministic `retrieve.py full` command
also rejects an absent or pending user review.
### Model-readable inputs

None.

Do not read `step2.json`, `adjudication.json`, `bundle.json`, `block.md`, the corpus,
the index, or the retrieval or rendering scripts. Their paths are sufficient to run
the fixed command.

### Command-only inputs

The deterministic command may consume:

- `scripts/run_case.py`;
- `scripts/retrieve.py`;
- `scripts/render.py`;
- `schema/disease_vocabulary.json`;
- `<work-dir>/step2.json`;
- `<work-dir>/adjudication.json`;
- the corpus and index identified by `<work-dir>/step2.json`.
### Required action

Run exactly:

```bash
python scripts/run_case.py full --work-dir <work-dir>
```

Step 4 deterministically retrieves gene-matched prognosis, treatment, and biomarker
cards whose exact `diseases` contain either the reviewed case disease or a direct
category-specific disease listed under that case disease in `retrieval_related`; a
legacy card with an empty disease array remains disease-unspecified and is retained.
Diagnosis cards and germline cards remain gene-only. `umbrella` and
`disease_ancestors` remain taxonomy/indexing metadata and are not consulted for this
retrieval expansion. Related retrieval is directional and non-transitive.

The wrapper deterministically writes:

- `<work-dir>/bundle.json`;
- `<work-dir>/block.md`.

Do not perform retrieval, filtering, validation, ordering, collapsing, truncation,
citation numbering, or formatting manually. Do not read, post-process, summarize, or
rewrite either file.
### Output

The terminal output is `<work-dir>/block.md`, exactly as written by the command.
`bundle.json` remains an internal deterministic intermediate.

## Step 6 — Write the NGS report

Run this step only when the user explicitly requests an NGS report.

Use a fresh bounded model session.
### Model-readable inputs

Read exactly:

1. the original case document supplied by the user;
2. `<work-dir>/block.md`;
3. `rules/agreed_reporting_rules`.

Read nothing else.

Do not read `case-input.json`, `step2.json`, `adjudication.json`, `bundle.json`, the corpus, index, disease vocabulary, prompts, scripts, schemas, source publications, examples, tests, documentation, live sources, or external references.
If any required input is missing, unreadable, or malformed, stop and report that error. Do not reconstruct `block.md`, rerun retrieval, browse for evidence, or substitute model knowledge.
### Source hierarchy

Apply the following boundaries:
- Use the supplied case only for patient identity, specimen information, clinical context, test results, variants, measurements, and other patient-specific facts.
- Use `block.md` as the exclusive source for interpretation of diagnosis, classification, prognosis, treatment, biomarkers, germline implications, and literature-derived claims.
- Use `rules/agreed_reporting_rules` only to decide what should be reported and how the report should be structured and worded.
- A reporting rule does not establish a patient fact or clinical assertion.
- Never add a clinical assertion, association, threshold, recommendation, drug, trial, classification rule, or citation from model knowledge.
- Do not strengthen, reconcile, or resolve statements beyond what `block.md` supports.
- Preserve uncertainty, disagreement, limitations, and qualifiers stated in `block.md`.
- Do not report an interpretation merely because it appears in the case document unless it is independently supported by `block.md`.
- Do not copy evidence-layer workflow metadata into the clinical report unless the reporting rules explicitly require it.
When the case and `block.md` appear inconsistent, do not silently repair the inconsistency. Represent only the interpretation supported by `block.md` and state the relevant limitation when required by the reporting rules.
### Required action

Write a complete NGS report that follows `rules/agreed_reporting_rules`.

The report must:
- describe only the supplied patient and specimen;
- include only findings present in the supplied case;
- base every interpretative statement exclusively on `block.md`;
- distinguish patient findings from literature-derived interpretation;
- retain clinically material qualifications and uncertainty;
- include only citations or references available in `block.md`;
- omit unsupported sections or state that no supported interpretation is available, as directed by the reporting rules.
### Output

Write exactly one file:

`<work-dir>/report.md`

The file must contain the report only. Do not include process commentary, source-audit notes, confidence commentary, alternative drafts, or a summary outside the report.

## Final delivery contract

Deliver only the artifact requested by the user.
### Evidence-block mode

After `run_case.py full` succeeds:

- return `<work-dir>/block.md`;
- do not independently regenerate, summarize, or modify it;
- normal UI text may identify the delivered filename.

### NGS-report mode

After Step 6 succeeds:

- return `<work-dir>/report.md`;
- do not also return `block.md` unless the user explicitly requested both;
- do not append commentary or an additional interpretation outside the report;
- normal UI text may identify the delivered filename.
### Both outputs explicitly requested

Return:

1. `<work-dir>/block.md`;
2. `<work-dir>/report.md`.

Do not combine them into one file.
