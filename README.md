# ngs_evidence_layer

A corpus-grounded evidence layer for myeloid NGS interpretation.

NEL uses `SKILL.md` to combine a supplied clinical case with the committed evidence
corpus and produce a concise NGS report with the current diagnosis-first workflow, while retaining the previous evidence-block/report workflow as `legacy-v1`. Reporting
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
   - run the first function-targeted validation case with `nel-validate-function 1A`.
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
| `ngs-report` | You want a complete NGS report using the default `categorical-v1` workflow. | `report-final.md` rendered in chat |
| `ngs-report --legacy` | You want the same report using the previous `legacy-v1` workflow. | `report-final.md` rendered in chat |
| `evidence-block --legacy` | You want the legacy retrieved evidence without a final report. | `evidence.md` |
| `evidence-block manual --legacy` | You want to review/revise the legacy proposed integrated diagnosis before full retrieval. | `evidence.md` |
| `evidence-to-report --legacy` | You already have a completed legacy evidence-block work directory and want the final report only. | `report-final.md` rendered in chat |
| `nel-demo example <N>` | You want to run one of the bundled demonstration cases. | Case, generated report, and expected result |
| `nel-validate <case-id>` | You want to run a bundled validation case on the current workflow. | External-marking ZIP + debug ZIP |
| `nel-validate-function <case-id>` | You want to test a specific reporting function using the functional validation suite. | Functional external-marking ZIP + debug ZIP |

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
4. refine the diagnostic routing and diagnosis conclusions;
5. retrieve the downstream evidence set;
6. build a citable evidence block;
7. draft and format the final report.

The current `ngs-report` uses `categorical-v1`. Use `ngs-report --diagnosis-first` (or `--diagnosis-first-v1`) for the previous diagnosis-first summarisation workflow, and `ngs-report --legacy` (or `--legacy-v1`) for the legacy pipeline. Legacy evidence-only/manual modes require an explicit legacy selector.

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

The default categorical final report:

- uses full sentences and independently synthesises diagnosis, prognosis, treatment, MRD-marker and germline categories;
- limits diagnosis to 70 words and each other drafted category to 50 words;
- skips categories deterministically when they contain no reportable rules;
- integrates detected variants into the diagnosis rather than emitting a separate variant section;
- prioritises clinically important conclusions and qualifications;
- uses Vancouver-style citations in square brackets;
- numbers references in order of first citation.

`categorical-v1` uses workflow-owned category formatting prompts. `--diagnosis-first` selects `diagnosis-first-v1`. Custom files
under `prompts/formatting/` apply only to legacy reporting modes such as
`ngs-report --legacy` and `evidence-to-report --legacy`.

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

## Current corpus

The current 0.2.3 corpus contains 29 active publications. Publications are grouped below by
the corpus version in which they were most recently accepted or modified, using
`latest_accepted_in_version` from `output/corpus/nel.index.json`. Card and acceptance-
version metadata are stored in the index; matching citation metadata, including DOI, is
stored in `output/corpus/nel.corpus.json`.

### Last modified in v0.2.3

| Publication key | DOI | Paper nickname | Contribution to corpus |
|---|---|---|---|
| `abelson-2018-predict-aml` | `10.1038/s41586-018-0317-6` | Abelson AML Prediction 2018 | Clonal-haematopoiesis features associated with future AML risk, including variant-specific clone-size effects. |
| `bolton-2020-chemo-ch` | `10.1038/s41588-020-00710-0` | Bolton 2020 — Cancer Therapy and Clonal Hematopoiesis | Effects of cancer therapy on clonal-haematopoiesis selection, including therapy-associated TP53, PPM1D, and CHEK2 clones. |
| `dinardo-2020-genotype-specific-venetoclax` | `10.1182/blood.2019003988` | DiNardo 2020 Venetoclax Response and Resistance in AML | Genotype-specific response, resistance, and relapse patterns after frontline venetoclax combinations in AML. |
| `dohner-2020-npm1-flt3-interaction` | `10.1182/blood.2019002697` | Döhner 2020 RATIFY NPM1/FLT3-ITD analysis | NPM1/FLT3-ITD genotype interactions, prognostic effects, and treatment associations in AML. |
| `fabre-2022-chip-dnmt3a` | `10.1038/s41586-022-04785-z` | Fabre 2022 Clonal Haematopoiesis Dynamics | Longitudinal clonal-haematopoiesis dynamics and mutation-specific associations with clonal expansion and malignant progression. |
| `flt3-ras-gilteritinib-resistance` | `10.1182/bloodadvances.2021006489` | ADMIRAL Molecular Profile 2022 | Molecular correlates of gilteritinib outcome and resistance in FLT3-mutated relapsed or refractory AML. |
| `idh-comutations-inhibitor-resistance` | `10.1038/s41467-021-22874-x` | IDH Inhibitor Resistance in AML 2021 | Co-mutation and stemness patterns associated with response and resistance to IDH inhibitors in AML. |
| `kraft-godley-2020-germline-guide` | `10.1182/blood.2020006910` | Kraft & Godley 2020 Germline NGS Review | Recognition and confirmation of potential germline variants detected during sequencing of haematological malignancies. |
| `malcovati-2017-ccus-foundation` | `10.1182/blood-2017-01-763425` | Malcovati 2017 CCUS Foundation | Mutation patterns supporting clonal cytopenia assessment and progression risk in unexplained cytopenias. |
| `mf-genomics-ruxolitinib-response` | `10.1038/leu.2014.3` | COMFORT-II MF Genomics 2014 | Driver and high-risk mutation associations with phenotype, prognosis, and ruxolitinib-related outcomes in myelofibrosis. |
| `mpn-genomics-interferon-response` | `10.1182/bloodadvances.2021004856` | DALIAH 2022 MPN genomics | Mutation-specific molecular and clinical responses to interferon-α versus hydroxyurea in myeloproliferative neoplasms. |
| `passamonti-2017-mysec-pm-secondary` | `10.1038/leu.2017.169` | MYSEC-PM 2017 secondary myelofibrosis | MYSEC-PM prognostic assessment and molecular features in post-PV and post-ET myelofibrosis. |
| `sf3b1-luspatercept-response` | `10.1016/s1470-2045(17)30615-0` | PACE-MDS 2017 luspatercept in MDS | SF3B1 and spliceosome-mutation associations with luspatercept erythroid response in lower-risk MDS. |
| `tefferi-2018-genomics-only-pmf` | `10.1038/s41375-018-0107-z` | Genetically Inspired Prognostic Scoring System (GIPPS) for primary myelofibrosis | GIPSS genetics-based prognostic scoring and high-risk molecular features in primary myelofibrosis. |
| `tet2-asxl1-hma-response` | `10.1182/blood-2014-06-582809` | Bejar 2014 TET2–HMA Response | TET2 and ASXL1 associations with hypomethylating-agent response and outcomes in MDS. |
| `tp53-lenalidomide-clonal-dynamics` | `10.1182/blood-2015-11-679167` | Mossner 2016 MDS clonal dynamics | MDS clonal evolution under therapy, progression biomarkers, and limitations of lymphocyte germline comparators. |
| `xie-2024-ccrs-ccus` | `10.1182/blood.2024024756` | Xie 2024 CCRS-CCUS | CCUS definitions and the clonal cytopenia risk score for progression to myeloid neoplasia. |

### Last modified in v0.2.2

| Publication key | DOI | Paper nickname | Contribution to corpus |
|---|---|---|---|
| `baliakas-2019-operational-germline-testing` | `10.1097/hs9.0000000000000321` | Nordic Germline Myeloid Guidelines 2019 | Germline predisposition recognition, testing indications, counselling, management, and follow-up guidance. |
| `bernard-2022-nejm-evidence-1-na` | `10.1056/evidoa2200008` | IPSS-M Prognostic score for MDS | Molecularly integrated IPSS-M prognostic risk assessment for myelodysplastic syndromes. |
| `feurstein-2021-myeloid-germline` | `10.1016/j.gim.2021.12.008` | Feurstein Germline Variant Interpretation Guide 2022 | Practical germline variant interpretation for haematological malignancy predisposition and related marrow-failure syndromes. |

### Last modified in v0.2.1

| Publication key | DOI | Paper nickname | Contribution to corpus |
|---|---|---|---|
| `alaggio-2022-leukemia-who5-lymphoid` | `10.1038/s41375-022-01620-2` | WHO-HAEM5 Lymphoid Neoplasms 2022 | WHO fifth-edition lymphoid classification, molecular diagnostic criteria, biomarkers, prognosis, and selected treatment implications. |
| `arber-2022-blood-140-1200` | `10.1182/blood.2022015850` | ICC Classification of Myeloid Neoplasms and Acute Leukemias | ICC myeloid and acute-leukaemia classification, molecular diagnostic criteria, prognostic features, biomarkers, and germline considerations. |
| `cloos-2026-blood-147-1147` | `10.1182/blood.2025031480` | ELN-DAVID AML MRD Guidelines 2025 | AML measurable residual disease assessment, interpretation, prognostic use, and management guidance. |

### Last modified in v0.2.0

| Publication key | DOI | Paper nickname | Contribution to corpus |
|---|---|---|---|
| `barbui-2015-blood-cancer-journal-5-e369` | `10.1038/bcj.2015.94` | IPSET-Thrombosis | Revised IPSET-thrombosis risk stratification and genotype-informed thrombosis and treatment considerations in essential thrombocythaemia. |
| `d-hner-2022-blood-140-1345` | `10.1182/blood.2022016867` | ELN 2022 Risk Classification for AML | ELN 2022 AML diagnosis, genetic risk classification, molecular biomarkers, treatment guidance, and germline considerations. |
| `d-hner-2024-blood-144-2169` | `10.1182/blood.2024025409` | ELN 2024 Less-Intensive AML Risk Classification | ELN 2024 genetic risk classification for adults with AML receiving less-intensive therapy. |
| `elena-2016-blood-128-1408` | `10.1182/blood-2016-05-714030` | CMML-specific CPSS-Mol score | CPSS-Mol molecular prognostic scoring and selected diagnostic features for chronic myelomonocytic leukaemia. |
| `khoury-2022-leukemia-36-1703` | `10.1038/s41375-022-01613-1` | WHO 5th Edition 2022 | WHO fifth-edition myeloid classification, molecular diagnostic criteria, prognosis, biomarkers, treatment, and germline guidance. |
| `tefferi-2018-journal-of-clinical-oncology-36-1769` | `10.1200/jco.2018.78.9867` | MIPSS70+ Version 2.0 Prognostic Score for Primary Myelofibrosis | MIPSS70+ version 2.0 mutation and karyotype-enhanced prognostic scoring for primary myelofibrosis. |

### Incompatible papers pending re-ingestion

These packages are incompatible with the current ingestion schema and do not contribute
evidence to the active corpus. They remain pending re-ingestion.

| Publication key | Status |
|---|---|
| `andrade-2018-tp53-gnomad` | Pending re-ingestion |
| `bernard-2020-tp53-mds` | Pending re-ingestion |
| `bluteau-2014-ankrd26` | Pending re-ingestion |
| `davidsson-2018-samd9-samd9l` | Pending re-ingestion |
| `drazer-2018-germline-vaf` | Pending re-ingestion |
| `galera-2018-gata2-germline` | Pending re-ingestion |
| `galli-2021-clone-metrics-ccus` | Pending re-ingestion |
| `grief-2012-gata-cebpa` | Pending re-ingestion |
| `hsu-2011-gata2-momomac` | Pending re-ingestion |
| `kessler-2022-large-biobank-genetics` | Pending re-ingestion |
| `noetzli-2015-etv6-phenotype` | Pending re-ingestion |
| `stahl-2021-independent-treatment-context` | Pending re-ingestion |
| `tefferi-2020-mipss-et-pv` | Pending re-ingestion |
| `weeks-2023-nejm-evidence-2-na` | Pending re-ingestion |
| `wlodarski-2016-gata2` | Pending re-ingestion |

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
