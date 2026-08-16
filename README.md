# ngs_evidence_layer

A corpus-grounded evidence layer for myeloid NGS interpretation.

NEL uses `SKILL.md` to combine a supplied clinical case with the committed evidence
corpus and produce a concise NGS report with the current diagnosis-first workflow, while retaining the previous evidence-block/report workflow as `legacy-v1`. Reporting
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
   - run the first validation case on the current workflow with `nel-validate 1A`; or
   - run the first function-targeted validation case with `nel-validate-function 1A`.
4. View the evidence card library in the [card browser](output/reports/card-browser.html).

## NGS reporting

Use one of the modes defined in `SKILL.md`.

| Mode | Use when | Output |
|---|---|---|
| `ngs-report` | You want a complete NGS report using the current accepted `diagnosis-first-v1` workflow. | `report-final.md` rendered in chat |
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

The current `ngs-report` uses the accepted diagnosis-first workflow. To run the previous pipeline, use `ngs-report --legacy` (or the immutable selector `ngs-report --legacy-v1`). Legacy evidence-only/manual modes require the same explicit legacy selector.

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

The current 0.2.1 corpus contains nine publications. Publications are grouped below by
the corpus version in which they were most recently accepted or modified, using
`latest_accepted_in_version` from `output/corpus/nel.index.json`. Complete citation,
card, and acceptance-version metadata are stored in that index.

### Last modified in v0.2.1

| Publication key | DOI | Paper nickname | Contribution to corpus |
|---|---|---|---|
| `cloos-2026-blood-147-1147` | `10.1182/blood.2025031480` | ELN-DAVID 2025 AML MRD Guidelines | AML measurable residual disease assessment and management guidance. |
| `arber-2022-blood-140-1200` | `10.1182/blood.2022015850` | ICC Classification | ICC myeloid classification and diagnostic criteria. |
| `alaggio-2022-leukemia-who5-lymphoid` | `10.1038/s41375-022-01620-2` | WHO-HAEM5 Lymphoid Neoplasms 2022 | WHO fifth-edition lymphoid classification and molecular diagnostic criteria. |

### Last modified in v0.2.0

| Publication key | DOI | Paper nickname | Contribution to corpus |
|---|---|---|---|
| `elena-2016-blood-128-1408` | `10.1182/blood-2016-05-714030` | CMML-specific CPSS-Mol score | Molecularly integrated prognostic risk assessment for CMML. |
| `d-hner-2022-blood-140-1345` | `10.1182/blood.2022016867` | ELN 2022 Risk Classification for AML | AML diagnosis, genetic risk classification, and management guidance. |
| `d-hner-2024-blood-144-2169` | `10.1182/blood.2024025409` | ELN 2024 Less-Intensive AML Risk Classification | AML genetic risk classification for less-intensive therapy. |
| `barbui-2015-blood-cancer-journal-5-e369` | `10.1038/bcj.2015.94` | IPSET-Thrombosis | Revised thrombosis-risk model for essential thrombocythaemia. |
| `tefferi-2018-journal-of-clinical-oncology-36-1769` | `10.1200/jco.2018.78.9867` | MIPSS70+ Version 2.0 Prognostic Score for Primary Myelofibrosis | Molecular and karyotype-enhanced prognostic scoring for primary myelofibrosis. |
| `khoury-2022-leukemia-36-1703` | `10.1038/s41375-022-01613-1` | WHO 5th Edition 2022 | WHO fifth-edition myeloid classification and diagnostic criteria. |

### Incompatible papers pending re-ingestion

The following publication packages are present in the corpus index but are incompatible with the current ingestion schema. They are not part of the accepted corpus and require re-ingestion before they can contribute evidence.

| Publication key | Status |
|---|---|
| `abelson-2018-predict-aml` | Pending re-ingestion |
| `andrade-2018-tp53-gnomad` | Pending re-ingestion |
| `baliakas-2019-operational-germline-testing` | Pending re-ingestion |
| `bernard-2020-tp53-mds` | Pending re-ingestion |
| `bernard-2022-nejm-evidence-1-na` | Pending re-ingestion |
| `bluteau-2014-ankrd26` | Pending re-ingestion |
| `bolton-2020-chemo-ch` | Pending re-ingestion |
| `davidsson-2018-samd9-samd9l` | Pending re-ingestion |
| `dinardo-2020-genotype-specific-venetoclax` | Pending re-ingestion |
| `dohner-2020-npm1-flt3-interaction` | Pending re-ingestion |
| `drazer-2018-germline-vaf` | Pending re-ingestion |
| `fabre-2022-chip-dnmt3a` | Pending re-ingestion |
| `feurstein-2021-myeloid-germline` | Pending re-ingestion |
| `flt3-ras-gilteritinib-resistance` | Pending re-ingestion |
| `galera-2018-gata2-germline` | Pending re-ingestion |
| `galli-2021-clone-metrics-ccus` | Pending re-ingestion |
| `grief-2012-gata-cebpa` | Pending re-ingestion |
| `hsu-2011-gata2-momomac` | Pending re-ingestion |
| `idh-comutations-inhibitor-resistance` | Pending re-ingestion |
| `kessler-2022-large-biobank-genetics` | Pending re-ingestion |
| `kraft-godley-2020-germline-guide` | Pending re-ingestion |
| `malcovati-2017-ccus-foundation` | Pending re-ingestion |
| `mf-genomics-ruxolitinib-response` | Pending re-ingestion |
| `mpn-genomics-interferon-response` | Pending re-ingestion |
| `noetzli-2015-etv6-phenotype` | Pending re-ingestion |
| `passamonti-2017-mysec-pm-secondary` | Pending re-ingestion |
| `sf3b1-luspatercept-response` | Pending re-ingestion |
| `stahl-2021-independent-treatment-context` | Pending re-ingestion |
| `tefferi-2018-genomics-only-pmf` | Pending re-ingestion |
| `tefferi-2020-mipss-et-pv` | Pending re-ingestion |
| `tet2-asxl1-hma-response` | Pending re-ingestion |
| `tp53-lenalidomide-clonal-dynamics` | Pending re-ingestion |
| `weeks-2023-nejm-evidence-2-na` | Pending re-ingestion |
| `wlodarski-2016-gata2` | Pending re-ingestion |
| `xie-2024-ccrs-ccus` | Pending re-ingestion |

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
