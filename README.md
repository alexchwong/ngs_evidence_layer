# ngs_evidence_layer

A corpus-grounded evidence layer for myeloid NGS interpretation.

NEL uses `SKILL.md` to combine a supplied clinical case with the committed evidence
corpus and produce either a citable evidence block or a concise NGS report. Reporting
is bounded to the supplied case, retrieved corpus evidence, and explicit reporting
rules; the model is not permitted to fill evidence gaps from general haematology
knowledge.

## NGS reporting

Use one of the modes defined in `SKILL.md`.

| Mode | Use when | Output |
|---|---|---|
| `ngs-report` | You want a complete NGS report from a new case. | `report-final.md` rendered in chat |
| `evidence-block` | You want the retrieved evidence without a final report. | `block.md` |
| `evidence-block manual` | You want to review or revise the proposed integrated diagnosis before full retrieval. | `block.md` |
| `evidence-to-report` | You already have a completed evidence-block work directory and want the final report only. | `report-final.md` rendered in chat |
| `nel-demo example <N>` | You want to run one of the bundled demonstration cases. | Case, generated report, and expected result |

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

## Current corpus

The current corpus contains 10 completed publications. A publication is repeated below
when it materially contributes to more than one category.

### Diagnosis / classification

| DOI | Nickname | Paper title | Contribution to corpus |
|---|---|---|---|
| `10.1038/s41375-022-01613-1` | WHO5 | The 5th edition of the World Health Organization Classification of Haematolymphoid Tumours: Myeloid and Histiocytic/Dendritic Neoplasms | WHO fifth-edition myeloid classification and diagnostic criteria. |
| `10.1182/blood.2022015850` | ICC | International Consensus Classification of Myeloid Neoplasms and Acute Leukemias: integrating morphologic, clinical, and genomic data | ICC myeloid classification and diagnostic criteria. |

### Prognosis

| DOI | Nickname | Paper title | Contribution to corpus |
|---|---|---|---|
| `10.1056/evidoa2200310` | CHRS | Prediction of Risk for Myeloid Malignancy in Clonal Hematopoiesis | CHRS predicts myeloid malignancy risk in clonal haematopoiesis. |
| `10.1038/bcj.2015.94` | revised IPSET-thrombosis | Practice-relevant revision of IPSET-thrombosis based on 1019 patients with WHO-defined essential thrombocythemia | Revised IPSET-thrombosis risk model for essential thrombocythaemia. |
| `10.1182/blood.2024025409` | ELN 2024 Less-Intensive | Genetic risk classification for adults with AML receiving less-intensive therapies: the 2024 ELN recommendations | ELN genetic risk groups for less-intensive AML therapy. |
| `10.1200/jco.2018.78.9867` | MIPSS70+ v2.0 | MIPSS70+ Version 2.0: Mutation and Karyotype-Enhanced International Prognostic Scoring System for Primary Myelofibrosis | MIPSS70+ v2.0 prognostic score for primary myelofibrosis. |
| `10.1182/blood-2016-05-714030` | CPSS-Mol | Integrating clinical features and genetic lesions in the risk assessment of patients with chronic myelomonocytic leukemia | CPSS-Mol integrates mutations into CMML prognostic risk. |
| `10.1056/evidoa2200008` | IPSS-M | Molecular International Prognostic Scoring System for Myelodysplastic Syndromes | IPSS-M molecular prognostic score for myelodysplastic syndromes. |
| `10.1182/blood.2022016867` | ELN 2022 | Diagnosis and management of AML in adults: 2022 recommendations from an international expert panel on behalf of the ELN | ELN AML genetic risk classification and prognostic guidance. |

### Treatment

| DOI | Nickname | Paper title | Contribution to corpus |
|---|---|---|---|
| `10.1182/blood.2022016867` | ELN 2022 | Diagnosis and management of AML in adults: 2022 recommendations from an international expert panel on behalf of the ELN | AML targeted treatment and management recommendations. |
| `10.1182/blood.2025031480` | ELN MRD 2025 | 2025 update on MRD in acute myeloid leukemia: a consensus document from the ELN-DAVID MRD Working Party | MRD-directed AML management and post-transplant maintenance recommendations. |

### Biomarkers

| DOI | Nickname | Paper title | Contribution to corpus |
|---|---|---|---|
| `10.1182/blood.2025031480` | ELN MRD 2025 | 2025 update on MRD in acute myeloid leukemia: a consensus document from the ELN-DAVID MRD Working Party | AML MRD assay selection, thresholds, timing, and interpretation. |
| `10.1182/blood.2022016867` | ELN 2022 | Diagnosis and management of AML in adults: 2022 recommendations from an international expert panel on behalf of the ELN | AML molecular testing and MRD biomarker guidance. |

### Germline

| DOI | Nickname | Paper title | Contribution to corpus |
|---|---|---|---|
| `10.1038/s41375-022-01613-1` | WHO5 | The 5th edition of the World Health Organization Classification of Haematolymphoid Tumours: Myeloid and Histiocytic/Dendritic Neoplasms | WHO germline predisposition framework for myeloid neoplasms. |
| `10.1182/blood.2022015850` | ICC | International Consensus Classification of Myeloid Neoplasms and Acute Leukemias: integrating morphologic, clinical, and genomic data | ICC germline predisposition genes and classification framework. |
| `10.1182/blood.2022016867` | ELN 2022 | Diagnosis and management of AML in adults: 2022 recommendations from an international expert panel on behalf of the ELN | Germline testing, counselling, and related-donor guidance. |

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
