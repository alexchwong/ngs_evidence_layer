---
name: ngs_evidence_layer
description: Produces a concise interpretative myeloid NGS report through a deny-by-default, corpus-bounded workflow with strict inputs and outputs at every step.
---

# NGS evidence layer reporting

## Purpose

Produce a concise interpretative myeloid NGS report for clinical haematologists from
one supplied case and the released evidence corpus. Literature-derived assertions
must come from corpus evidence. Patient-specific assertions must come from the
supplied case.

The corpus is an immutable input. This skill does not create, edit, audit, or
incorporate evidence cards.

## Mandatory file-access policy

File access is **deny by default**. After reading this skill, at each step read only
the files listed under that step's **Model-readable inputs**.

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
summaries, or convenience copies. Do not modify an output after a deterministic
command writes it. If a required input is missing, unreadable, malformed, or
inconsistent with its contract, stop and report that error. Do not browse for a
replacement or infer the missing content.

Use a fresh bounded model session for Step 3. Use another fresh bounded model session
for Step 6. Each session receives exactly the inputs named by its step.

## Missing and unreported results

Treat a reported test result as complete unless the case says that it is partial,
selected, limited, abbreviated, pending, or otherwise incomplete. If an abnormal
finding is not listed in a complete test result, treat it as negative for that test.

Do not assume that an unmentioned test was performed. Keep every inferred negative
within the limits of the reported test. A negative sequencing result does not also
exclude a copy-number change, rearrangement, or other finding unless the case says
that the test assessed it.

If cytogenetic results are not supplied, assume normal conventional cytogenetics for
the interpretation. This is a workflow assumption, not a patient result. State the
assumption in the final report. Do not say that cytogenetics were performed or that a
specific cytogenetic abnormality was formally excluded.

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
  by one exact allowed value from the disease vocabulary; do not upgrade it from
  model knowledge;
- `genes`: genes strictly from the NGS result block, not genes mentioned only in the
  history, differential, assay description, or another test;
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

Write exactly one file, `case-input.json`, containing JSON only with exactly these
three top-level fields:

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

Do not include explanatory prose or additional top-level fields.

## Step 2 — Retrieve diagnosis evidence

### Model-readable inputs

Read exactly:

1. `case-input.json`.

Read nothing else. In particular, do not inspect the retrieval script, corpus, index,
or disease vocabulary.

### Command-only inputs

The following may be consumed by the deterministic command but must not be read by
the model:

- `scripts/retrieve.py`;
- `output/corpus/nel.corpus.json`;
- `output/corpus/nel.index.json`.

### Required action

Copy `genes` and `provisional_disease` exactly from `case-input.json` into this
command. Pass the same file as the case-facts input:

```bash
python scripts/retrieve.py diagnosis \
  --genes <genes copied from case-input.json> \
  --provisional-disease <value copied from case-input.json> \
  --case-facts case-input.json \
  --corpus output/corpus/nel.corpus.json \
  --index output/corpus/nel.index.json \
  --output step2.json
```

Do not perform diagnostic selection or interpretation in this step.

### Output

The only output is `step2.json`, exactly as written by the command. Do not read,
edit, summarize, or supplement it in this step.

## Step 3 — Adjudicate the diagnosis

Use a fresh bounded model session.

### Model-readable inputs

Read exactly:

1. `prompts/diagnostic_adjudication_prompt.md`;
2. `step2.json`.

Read nothing else. Do not read the original case, `case-input.json`, disease
vocabulary, corpus, index, reporting rules, scripts, examples, or repository
documentation.

### Required action

Follow `prompts/diagnostic_adjudication_prompt.md` exactly. Treat `step2.json` as the
complete patient-fact and diagnosis-evidence boundary. Do not add a fact, rule,
threshold, exclusion, definition, or qualifier from memory.

Apply the recorded `test_result_status` and `workflow_assumption` facts as directed by
the prompt. Do not make the diagnosis indeterminate only because a card mentions a
competing diagnosis or precedence rule. Consider the competing diagnosis when a
supplied mutation, cytogenetic or FISH finding, copy-number result, morphology, blood
count, or clinical feature suggests that it may be present. Its mention in a card is
not by itself enough to raise it.

### Output

Write exactly one file, `adjudication.json`. It must contain JSON only and exactly the
output shape required by `prompts/diagnostic_adjudication_prompt.md`. Do not add prose
or extra fields.

## Step 4 — Retrieve the full evidence bundle

### Model-readable inputs

None.

Do not read `step2.json`, `adjudication.json`, the corpus, the index, or the retrieval
script. Their paths are sufficient to run the fixed command.

### Command-only inputs

The deterministic command may consume:

- `scripts/retrieve.py`;
- `step2.json`;
- `adjudication.json`;
- the corpus and index identified by `step2.json`.

### Required action

Run exactly:

```bash
python scripts/retrieve.py full \
  --diagnosis-result step2.json \
  --adjudication-result adjudication.json \
  --output bundle.json
```

Do not perform retrieval, filtering, validation, or interpretation manually.

### Output

The only output is `bundle.json`, exactly as written by the command. Do not read,
edit, summarize, or supplement it in this step.

## Step 5 — Render the evidence block

### Model-readable inputs

None.

Do not read `bundle.json` or inspect the rendering script. Their paths are sufficient
to run the fixed command.

### Command-only inputs

The deterministic command may consume:

- `scripts/render.py`;
- `bundle.json`.

### Required action

Run exactly:

```bash
python scripts/render.py --bundle bundle.json --output block.md
```

Do not order, collapse, truncate, number, or format evidence manually.

### Output

The only output is `block.md`, exactly as written by the command. Do not read, edit,
summarize, or supplement it in this step.

## Step 6 — Write the interpretative report

Use a fresh bounded model session.

### Model-readable inputs

Read exactly:

1. the same one case document supplied to Step 1;
2. `block.md`;
3. `rules/agreed_reporting_rules.md`.

Read nothing else. Do not read `case-input.json`, `step2.json`,
`adjudication.json`, `bundle.json`, the diagnostic adjudication prompt, disease
vocabulary, corpus, index, scripts, source publications, ingestion material,
documentation, examples, expected outputs, tests, or logs.

### Required action

Treat the case document as the complete patient-fact boundary, `block.md` as the
complete literature-evidence and citation boundary, and
`rules/agreed_reporting_rules.md` as the complete report-synthesis policy.

Apply the reporting rules in this order, omitting sections that are not relevant:

1. Integrated diagnosis and classification
2. Prognostic significance
3. Clinically actionable implications
4. MRD implications
5. Possible germline predisposition

For each included section:

- lead with the clinically important conclusion;
- integrate supplied patient facts with relevant rendered evidence rather than
  copying the evidence block line by line;
- preserve every material disease, population, treatment, allelic, variant, analysis,
  classifier, threshold, branch, and exclusion qualifier;
- cite each literature-derived conclusion using only the deterministic references in
  `block.md`;
- distinguish established conclusions from possibilities, unresolved conflicts, and
  missing inputs;
- name required variables when a diagnosis, score, tier, allelic state, or management
  implication cannot be established;
- do not include hypothetical exclusions that are not raised by the case;
- mention a missing test or unresolved exclusion only when it could realistically
  change the diagnosis in this patient;
- if normal conventional cytogenetics were assumed because cytogenetic results were
  not supplied, state exactly: "This interpretation assumes normal conventional
  cytogenetics because cytogenetic results were not supplied.";
- treat a gene reported as not assessed as outside this corpus version's coverage,
  not as clinically negative or considered and cleared;
- surface any truncation or corpus limitation material to interpretation.

Do not invent literature, patient facts, approval status, jurisdiction, assay
performance, quotations, or an ACMG/ClinGen/VICC conclusion. Do not supplement the
three inputs from memory or another source. If the inputs conflict or are
insufficient, state the bounded uncertainty in the report; do not search for more
information.

Verify the report privately against only these same three inputs. Do not open an
intermediate file during verification.

### Output

Return only the final interpretative report in Markdown. If the user explicitly
requests a file, write exactly one file, `report.md`, containing only that report.
Do not return process commentary, JSON, an evidence appendix, copied cards, or any
other artefact.
