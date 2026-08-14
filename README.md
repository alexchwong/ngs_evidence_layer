# ngs_evidence_layer

A corpus-grounded evidence layer for myeloid NGS interpretation.

NEL uses `SKILL.md` to combine a supplied clinical case with the committed evidence
corpus and produce either a citable evidence block or a concise NGS report. Reporting
is bounded to the supplied case, retrieved corpus evidence, and explicit reporting
rules; the model is not permitted to fill evidence gaps from general haematology
knowledge.

## Quick start for end users

1. Open the repository's GitHub **Releases** tab and download the latest release or
   pre-release ZIP file.
2. Make the downloaded skill available to your preferred chat application using one of
   these options:
   - `Claude`: upload the zip file as a skill in Claude;
   - `Any UI that supports skills.md`: use it as a skill in any UI that supports `SKILL.md` skills; or
   - `ChatGPT`: create a ChatGPT project and upload the ZIP file to the project as a source
     document. For ChatGPT, also add a source document named `master-prompt.txt` containing:

     ```text
     If the user requests `ngs-*`, treat the attached zip file "ngs_evidence_layer*.zip" as a skill.
     Read the skill.md to understand the skill
     ```

3. Start a chat session in one of these ways:
   - paste the clinical and morphological details and the NGS result, then add
     `ngs-report` on a line by itself;
   - run the first demonstration case with `nel-demo example 1`; or
   - run the first validation case with `nel-validate 1A`.

## NGS reporting

Use one of the modes defined in `SKILL.md`.

| Mode | Use when | Output |
|---|---|---|
| `ngs-report` | You want a complete NGS report from a new case. | `report-final.md` rendered in chat |
| `evidence-block` | You want the retrieved evidence without a final report. | `evidence.md` |
| `evidence-block manual` | You want to review or revise the proposed integrated diagnosis before full retrieval. | `evidence.md` |
| `evidence-to-report` | You already have a completed evidence-block work directory and want the final report only. | `report-final.md` rendered in chat |
| `nel-demo example <N>` | You want to run one of the bundled demonstration cases. | Case, generated report, and expected result |
| `nel-validate <case-id>` | You want to run a bundled validation case and score the generated report. | Generated report and marking result |

### Generate a report

Ask the model to run:

```text
ngs-report

<clinical case>
```

The case can contain the available clinical context, morphology, blood counts,
cytogenetics, molecular findings, treatment context, and other information relevant to
interpretation.

NEL will:

1. preserve the supplied case;
2. structure the case for deterministic retrieval;
3. retrieve diagnosis evidence;
4. adjudicate an integrated diagnosis;
5. retrieve the full evidence set;
6. build a citable evidence block;
7. draft and format the final report.

Automatic `ngs-report` does not pause for diagnosis confirmation. Use
`evidence-block manual` when you want to review the proposed integrated diagnosis
before downstream retrieval.

### Working directory

By default, NEL creates a unique system temporary working directory and retains it after
the workflow finishes. To keep a new workflow under the repository's ignored `temp/`
directory instead, include the exact modifier `->project`, for example:

```text
ngs-report ->project

<clinical case>
```

NEL does not infer `->project` from natural-language requests. You may also explicitly
supply another working directory. `evidence-to-report` always requires an existing work
directory containing the completed evidence-block outputs.

### Report format

The default final report:

- is no more than 200 words, excluding references;
- uses full sentences;
- opens with the detected genes in alphabetical order, with variant type or recognised
  hotspot name and VAF;
- gives the exact variant when a gene is being reported as a biomarker;
- prioritises clinically important conclusions and qualifications;
- uses Vancouver-style citations in square brackets;
- numbers references in order of first citation.

For `ngs-report` or `evidence-to-report`, a different formatting prompt may be
specified at the start of the workflow if that prompt is present under
`prompts/formatting/`.

### Evidence-only use

Use:

```text
evidence-block

<clinical case>
```

to return `evidence.md` without generating a final NGS report.

Use:

```text
evidence-block manual

<clinical case>
```

when you want the model to present its proposed integrated diagnosis for review before
full evidence retrieval.

### Convert an existing evidence block to a report

If Steps 1–5 have already been completed, provide the retained work directory and run:

```text
evidence-to-report
```

NEL verifies that the required `case.md` and `evidence.md` are present, then performs only
the reporting steps.

### Demo mode

Run:

```text
nel-demo example 1
```

through:

```text
nel-demo example 6
```

to execute a bundled example through the normal reporting workflow. The expected result
is not read until the generated report is complete.

### Validation mode

Run `nel-validate <case-id>` (for example, `nel-validate 1A`) to execute a bundled
validation case. Marking criteria are withheld until the report is complete, then used
to score the generated report. Available case IDs are:

`1A`, `1B`, `1C`, `1D`, `1E`; `2A`, `2B`, `2C`, `2D`, `2E`;
`3A`, `3B`, `3C`, `3D`; `4A`, `4B`, `4C`, `4D`; `5A`, `5B`, `5C`, `5D`.

## Current corpus

The current 0.2.1 corpus contains nine publications. Publications are grouped below by
the corpus version in which they were most recently accepted or modified, using
`latest_accepted_in_version` from `output/corpus/nel.index.json`. Complete citation,
card, and acceptance-version metadata are stored in that index.

### Last modified in v0.2.1

| DOI | Paper nickname | Contribution to corpus |
|---|---|---|
| `10.1182/blood.2025031480` | ELN-DAVID 2025 AML MRD Guidelines | AML measurable residual disease assessment and management guidance. |
| `10.1182/blood.2022015850` | ICC Classification | ICC myeloid classification and diagnostic criteria. |
| `10.1038/s41375-022-01620-2` | WHO-HAEM5 Lymphoid Neoplasms 2022 | WHO fifth-edition lymphoid classification and molecular diagnostic criteria. |

### Last modified in v0.2.0

| DOI | Paper nickname | Contribution to corpus |
|---|---|---|
| `10.1182/blood-2016-05-714030` | CMML-specific CPSS-Mol score | Molecularly integrated prognostic risk assessment for CMML. |
| `10.1182/blood.2022016867` | ELN 2022 Risk Classification for AML | AML diagnosis, genetic risk classification, and management guidance. |
| `10.1182/blood.2024025409` | ELN 2024 Less-Intensive AML Risk Classification | AML genetic risk classification for less-intensive therapy. |
| `10.1038/bcj.2015.94` | IPSET-Thrombosis | Revised thrombosis-risk model for essential thrombocythaemia. |
| `10.1200/jco.2018.78.9867` | MIPSS70+ Version 2.0 Prognostic Score for Primary Myelofibrosis | Molecular and karyotype-enhanced prognostic scoring for primary myelofibrosis. |
| `10.1038/s41375-022-01613-1` | WHO 5th Edition 2022 | WHO fifth-edition myeloid classification and diagnostic criteria. |
## Important boundaries

- NEL reports only what the supplied case and retrieved corpus support.
- Different publications can coexist in the corpus even when their recommendations differ.
- NEL does not query live approval, drug, guideline, or other external databases during case interpretation.
- Evidence that is absent from the corpus is not supplied from model memory.
- The evidence corpus is distinct from reporting rules and formatting prompts: changing report formatting does not change corpus evidence.

## Other documentation

- [`INGEST.md`](INGEST.md) — add, review, accept, and re-ingest publications.
- [`DEVEL.md`](DEVEL.md) — prompt maintenance, testing, versioning, and releases.
- [`NEWS.md`](NEWS.md) — changelog.
