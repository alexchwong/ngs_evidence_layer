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
| `evidence-block` | You want the retrieved evidence without a final report. | `block.md` |
| `evidence-block manual` | You want to review or revise the proposed integrated diagnosis before full retrieval. | `block.md` |
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

### Report format

The default final report:

- is no more than 200 words, excluding references;
- uses full sentences;
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

to return `block.md` without generating a final NGS report.

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

NEL verifies that the required `case.md` and `block.md` are present, then performs only
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

`1A`, `1B`, `1C`, `1D`; `2A`, `2B`, `2C`; `3A`, `3B`, `3C`; `4A`, `4B`, `4C`;
`5A`, `5B`, `5C`; `6A`, `6B`, `6C`; `7A`, `7B`, `7C`; `8A`, `8B`, `8C`;
`9A`, `9B`, `9C`; `10A`, `10B`, `10C`; `11A`, `11B`, `11C`.

## Current corpus

The current corpus contains 23 completed publications: 10 introduced in v0.1.5 and 13
introduced in v0.1.6. The release in which each paper first entered the corpus is stored
in `nel.index.json` as `accepted_in_version`.

### v0.1.5

| DOI | Nickname | Paper title | Contribution to corpus |
|---|---|---|---|
| `10.1038/s41375-022-01613-1` | WHO5 | The 5th edition of the World Health Organization Classification of Haematolymphoid Tumours: Myeloid and Histiocytic/Dendritic Neoplasms | WHO fifth-edition myeloid classification and diagnostic criteria. |
| `10.1182/blood.2022015850` | ICC | International Consensus Classification of Myeloid Neoplasms and Acute Leukemias: integrating morphologic, clinical, and genomic data | ICC myeloid classification and diagnostic criteria. |
| `10.1056/evidoa2200310` | CHRS | Prediction of Risk for Myeloid Malignancy in Clonal Hematopoiesis | CHRS predicts myeloid malignancy risk in clonal haematopoiesis. |
| `10.1038/bcj.2015.94` | revised IPSET-thrombosis | Practice-relevant revision of IPSET-thrombosis based on 1019 patients with WHO-defined essential thrombocythemia | Revised IPSET-thrombosis risk model for essential thrombocythaemia. |
| `10.1182/blood.2024025409` | ELN 2024 Less-Intensive | Genetic risk classification for adults with AML receiving less-intensive therapies: the 2024 ELN recommendations | ELN genetic risk groups for less-intensive AML therapy. |
| `10.1200/jco.2018.78.9867` | MIPSS70+ v2.0 | MIPSS70+ Version 2.0: Mutation and Karyotype-Enhanced International Prognostic Scoring System for Primary Myelofibrosis | MIPSS70+ v2.0 prognostic score for primary myelofibrosis. |
| `10.1182/blood-2016-05-714030` | CPSS-Mol | Integrating clinical features and genetic lesions in the risk assessment of patients with chronic myelomonocytic leukemia | CPSS-Mol integrates mutations into CMML prognostic risk. |
| `10.1056/evidoa2200008` | IPSS-M | Molecular International Prognostic Scoring System for Myelodysplastic Syndromes | IPSS-M molecular prognostic score for myelodysplastic syndromes. |
| `10.1182/blood.2022016867` | ELN 2022 | Diagnosis and management of AML in adults: 2022 recommendations from an international expert panel on behalf of the ELN | ELN AML genetic risk classification and prognostic guidance. |
| `10.1182/blood.2025031480` | ELN MRD 2025 | 2025 update on MRD in acute myeloid leukemia: a consensus document from the ELN-DAVID MRD Working Party | MRD-directed AML management and post-transplant maintenance recommendations. |

### v0.1.6

| DOI | Nickname | Paper title | Contribution to corpus |
|---|---|---|---|
| `10.1182/blood.2019003988` | VEN genotype response | Molecular patterns of response and treatment failure after frontline venetoclax combinations in older patients with AML | Genotype-specific response and resistance to frontline venetoclax combinations. |
| `10.1182/blood.2019002697` | NPM1/FLT3-ITD | Impact of NPM1/FLT3-ITD genotypes defined by the 2017 European LeukemiaNet in patients with acute myeloid leukemia | Prognostic interaction of NPM1 and FLT3-ITD in AML. |
| `10.1182/bloodadvances.2021006489` | ADMIRAL molecular | Molecular profile of FLT3-mutated relapsed/refractory patients with AML in the phase 3 ADMIRAL study of gilteritinib | Molecular predictors and resistance patterns during gilteritinib therapy. |
| `10.1038/s41467-021-22874-x` | IDH inhibitor resistance | Leukemia stemness and co-occurring mutations drive resistance to IDH inhibitors in acute myeloid leukemia | Co-mutation and stemness modifiers of IDH-inhibitor response and resistance. |
| `10.1038/leu.2014.3` | PMF driver genotype | CALR vs JAK2 vs MPL-mutated or triple-negative myelofibrosis: clinical, cytogenetic and molecular comparisons | Driver genotype and adverse molecular features in myelofibrosis. |
| `10.1182/bloodadvances.2021004856` | MPN interferon genomics | Genomic profiling of a randomized trial of interferon-α vs hydroxyurea in MPN reveals mutation-specific responses | Mutation-specific response to interferon versus hydroxyurea in MPN. |
| `10.1038/leu.2017.169` | MYSEC-PM | A clinical-molecular prognostic model to predict survival in patients with post polycythemia vera and post essential thrombocythemia myelofibrosis | MYSEC-PM prognosis for post-PV and post-ET myelofibrosis. |
| `10.1016/S1470-2045(17)30615-0` | PACE-MDS | Luspatercept for the treatment of anaemia in patients with lower-risk myelodysplastic syndromes (PACE-MDS): a multicentre, open-label phase 2 dose-finding study with long-term extension study | SF3B1-associated response to luspatercept in lower-risk MDS. |
| `10.1182/bloodadvances.2020003734` | R/R AML venetoclax | Clinical and molecular predictors of response and survival following venetoclax therapy in relapsed/refractory AML | Molecular predictors of venetoclax response and survival in R/R AML. |
| `10.1038/s41375-018-0107-z` | GIPSS | GIPSS: genetically inspired prognostic scoring system for primary myelofibrosis | Genetics-only prognostic score for primary myelofibrosis. |
| `10.1111/bjh.16380` | MIPSS-ET/PV | Mutation-enhanced international prognostic systems for essential thrombocythaemia and polycythaemia vera | Mutation-enhanced survival models for ET and PV. |
| `10.1182/blood-2014-06-582809` | TET2 HMA response | TET2 mutations predict response to hypomethylating agents in myelodysplastic syndrome patients | TET2 and co-mutation effects on HMA response in MDS. |
| `10.1182/blood-2015-11-679167` | MDS clonal dynamics | Mutational hierarchies in myelodysplastic syndromes dynamically adapt and evolve upon therapy response and failure | Therapy-associated clonal dynamics, including TP53 and lenalidomide. |

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
