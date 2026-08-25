# ngs_evidence_layer

A corpus-grounded evidence layer for myeloid NGS interpretation.

NEL uses `SKILL.md` to combine a supplied clinical case with the committed evidence
corpus and produce a concise NGS report with the default `terraced-v6` workflow, while retaining older registered workflows for explicit selection. Reporting
is bounded to the supplied case, retrieved corpus evidence, and explicit reporting
rules; the model is not permitted to fill evidence gaps from general haematology
knowledge.

## Quick start

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
   - run the first validation case on the current workflow with `nel-validate 1A`; or
   - run the first function-targeted validation case with `nel-validate-function 1A`; or
   - run the consolidated regression suite with `nel-validate-brief 1`.
4. View the evidence card library in the [card browser](output/reports/card-browser.html).

## Contents

- [NGS reporting](#ngs-reporting)
- [Current corpus](#current-corpus)
- [Important boundaries](#important-boundaries)
- [Other documentation](#other-documentation)

## NGS reporting

Use one of the modes defined in `SKILL.md`.

| Mode | Use when | Output |
|---|---|---|
| `ngs-report` | You want a complete NGS report using the default `terraced-v6` workflow. | `report-final.md` rendered in chat |
| `ngs-report --legacy` | You want the same report using the previous `legacy-v1` workflow. | `report-final.md` rendered in chat |
| `evidence-block --legacy` | You want the legacy retrieved evidence without a final report. | `evidence.md` |
| `evidence-block manual --legacy` | You want to review/revise the legacy proposed integrated diagnosis before full retrieval. | `evidence.md` |
| `evidence-to-report --legacy` | You already have a completed legacy evidence-block work directory and want the final report only. | `report-final.md` rendered in chat |
| `nel-demo example <N>` | You want to run one of the bundled demonstration cases. | Case, generated report, and expected result |
| `nel-validate <case-id>` | You want to run a bundled validation case on the current workflow. | External-marking ZIP + debug ZIP |
| `nel-validate-function <case-id>` | You want to test a specific reporting function using the functional validation suite. | Functional external-marking ZIP + debug ZIP |
| `nel-validate-brief <case-id>` | You want the consolidated 10-case clinical regression suite. | Brief-suite external-marking ZIP + debug ZIP |

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

1. preserve and structure the supplied case;
2. run independent WHO5, ICC, and authoritative second-WHO5 diagnostic assessments;
3. complete prognosis, treatment, MRD/biomarker, and germline reasoning;
4. resolve supporting evidence across reportable reasons;
5. independently audit those evidence assignments;
6. adjudicate only resolver/auditor disagreements;
7. construct deterministic, citable report blocks;
8. synthesize and render the final report against the original case context.

The current `ngs-report` uses `terraced-v6`. Use `ngs-report --diagnosis-first` (or `--diagnosis-first-v1`) for the older diagnosis-first workflow, `ngs-report --terraced-v1` through `--terraced-v5` for earlier terraced workflows, and `ngs-report --legacy` (or `--legacy-v1`) for the legacy pipeline. Legacy evidence-only/manual modes require an explicit legacy selector.

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

The default `terraced-v6` final report:

- synthesises only conclusions retained by the deterministic evidence-resolution and audit pipeline;
- uses the original case context during final prose synthesis without permitting new clinical conclusions;
- suppresses non-reportable negative or uncertain domain findings according to workflow settings;
- preserves evidence provenance and any semantic dissent outside the final clinical prose;
- uses Vancouver-style citations in square brackets;
- numbers references in order of first citation.

`terraced-v6` owns its reporting contracts under `workflows/terraced_v6/`. `--diagnosis-first` selects `diagnosis-first-v1`. Custom files under `prompts/formatting/` apply only to legacy reporting modes such as `ngs-report --legacy` and `evidence-to-report --legacy`.

### Evidence-only use

Use:

```text
evidence-block --legacy

<clinical case>
```

to return `evidence.md` without generating a final NGS report.

Use:

```text
evidence-block manual --legacy

<clinical case>
```

when you want the model to present its proposed integrated diagnosis for review before
full evidence retrieval.

### Convert an existing evidence block to a report

If Steps 1–5 have already been completed, provide the retained work directory and run:

```text
evidence-to-report --legacy
```

This legacy-only mode verifies that the required `case.md` and `evidence.md` are present, then performs only
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

Run `nel-validate <case-id>` (for example, `nel-validate 1A`) to execute the existing
validation suite in `validation/case_summary.md`. Marking criteria are withheld until the
report is complete. Available legacy case IDs are:

`1A`, `1B`, `1C`, `1D`, `1E`; `2A`, `2B`, `2C`, `2D`, `2E`;
`3A`, `3B`, `3C`, `3D`; `4A`, `4B`, `4C`, `4D`; `5A`, `5B`, `5C`, `5D`.

Run `nel-validate-function <case-id>` to execute the parallel function-targeted suite in
`validation/case_functional.md`. Its case IDs are:

`1A`-`1H` (AML); `2A`-`2G` (MDS with 12% blasts); `3A`-`3G`
(thrombocytosis/leukocytosis without marrow); and `4A`-`4D` (miscellaneous).

`validation/case_functional_manifest.md` documents the reporting function isolated by each
functional case. It is evaluator/developer-only and is never supplied to the report-generation
model or included in the external marking ZIP.

Run `nel-validate-brief <case-id>` to execute the consolidated regression suite in
`validation/validation_brief.md`. The consolidated brief suite contains 10 cases with IDs
`1` through `10`; it is intended for high-yield end-to-end regression rather than exhaustive
gene/disease content coverage.

## Current corpus

The current 0.2.4 corpus contains 12 active publications. Publications are grouped below by
`latest_accepted_in_version` from `output/corpus/nel.index.json`. Card and acceptance-version
metadata are stored in the index; matching citation metadata, including DOI, is stored in
`output/corpus/nel.corpus.json`.

### Last modified in v0.2.4

| Publication key | DOI | Paper nickname | Contribution to corpus |
|---|---|---|---|
| `alaggio-2022-leukemia-who5-lymphoid` | `10.1038/s41375-022-01620-2` | WHO5 Lymphoid Classification 2022 | WHO fifth-edition lymphoid classification, molecular diagnostic criteria, biomarkers, prognosis, treatment implications, and germline considerations. |
| `arber-2022-blood-140-1200` | `10.1182/blood.2022015850` | ICC Classification 2022 | ICC myeloid and acute-leukaemia classification, molecular diagnostic criteria, prognosis, biomarkers, treatment, and germline considerations. |
| `barbui-2015-blood-cancer-journal-5-e369` | `10.1038/bcj.2015.94` | Revised IPSET-thrombosis for ET (Barbui 2015) | Revised IPSET-thrombosis risk stratification and genotype-informed thrombosis assessment in essential thrombocythaemia. |
| `bernard-2022-nejm-evidence-1-na` | `10.1056/evidoa2200008` | IPSS-M Risk stratification for myelodysplastic neoplasm (MDS) | Molecularly integrated IPSS-M prognostic assessment with selected biomarker, treatment, and germline implications in MDS. |
| `cloos-2026-blood-147-1147` | `10.1182/blood.2025031480` | ELN-DAVID 2025 AML MRD recommendations | AML measurable residual disease marker selection, interpretation, prognostic use, and management guidance. |
| `d-hner-2022-blood-140-1345` | `10.1182/blood.2022016867` | ELN 2022 AML Recommendations | ELN 2022 AML diagnosis, genetic risk classification, molecular biomarkers, treatment guidance, and germline considerations. |
| `d-hner-2024-blood-144-2169` | `10.1182/blood.2024025409` | 2024 ELN Less-Intensive genetic risk classification for AML | ELN 2024 genetic risk classification and treatment-context associations for adults receiving less-intensive AML therapy. |
| `elena-2016-blood-128-1408` | `10.1182/blood-2016-05-714030` | Elena 2016 CPSS-Mol | CPSS-Mol molecular prognostic scoring and selected diagnostic features for chronic myelomonocytic leukaemia. |
| `guglielmelli-2017-mipss70-pmf` | `10.1200/jco.2017.76.4886` | MIPSS70 / MIPSS70-plus risk stratification for primary myelofibrosis | MIPSS70 and MIPSS70-plus mutation-enhanced prognostic risk stratification for transplantation-age primary myelofibrosis. |
| `khoury-2022-leukemia-36-1703` | `10.1038/s41375-022-01613-1` | WHO5 2022 Myeloid Classification | WHO fifth-edition myeloid classification, molecular diagnostic criteria, prognosis, biomarkers, treatment, and germline guidance. |
| `tefferi-2018-journal-of-clinical-oncology-36-1769` | `10.1200/jco.2018.78.9867` | MIPSS70+ Version 2.0 (Tefferi 2018) | MIPSS70+ version 2.0 mutation- and karyotype-enhanced prognostic scoring for primary myelofibrosis. |
| `weeks-2023-nejm-evidence-2-na` | `10.1056/evidoa2200310` | CHRS for CHIP/CCUS 2023 | CHIP/CCUS definitions and genotype-informed clonal-haematopoiesis risk prediction for progression to myeloid neoplasia. |

## Important boundaries

- NEL reports only what the supplied case and retrieved corpus support.
- Different publications can coexist in the corpus even when their recommendations differ.
- NEL does not query live approval, drug, guideline, or other external databases during case interpretation.
- Evidence that is absent from the corpus is not supplied from model memory.
- The evidence corpus is distinct from reporting rules and formatting prompts: changing report formatting does not change corpus evidence.

## Other documentation

- [`INGEST.md`](INGEST.md) — add, review, accept, and re-ingest publications.
- [`WORKFLOW.md`](WORKFLOW.md) — reporting-workflow separation, cloning, modification, validation, and promotion.
- [`DEVEL.md`](DEVEL.md) — prompt maintenance, testing, versioning, and releases.
- [`NEWS.md`](NEWS.md) — changelog.
