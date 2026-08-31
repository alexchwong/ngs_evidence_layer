# Current corpus

The current 0.3.0 corpus contains 19 active publications. Publications are grouped below by
`latest_accepted_in_version` from `output/corpus/nel.index.json`. Card and acceptance-version
metadata are stored in the index; matching citation metadata, including DOI, is stored in
`output/corpus/nel.corpus.json`.

### Last modified in v0.2.5
| Publication key | DOI | Paper nickname | Contribution to corpus |
|---|---|---|---|
| `baliakas-2019-operational-germline-testing` | `10.1097/hs9.0000000000000321` | Nordic Germline Predisposition Guidelines 2019 | Adult germline predisposition recognition, genetic testing, clinical management, donor selection, surveillance, and family counselling guidance. |
| `bernard-2020-tp53-mds` | `10.1038/s41591-020-1008-z` | Bernard TP53 Allelic State in MDS 2020 | TP53 monoallelic versus multi-hit state in MDS, with diagnostic, prognostic, leukemic-transformation, and treatment-response implications. |
| `kraft-godley-2020-germline-guide` | `10.1182/blood.2020006910` | Kraft–Godley Germline NGS Guide 2020 | Recognition of potential germline variants from haematologic NGS using clinical context, VAF, persistence, and confirmatory-testing principles. |
| `malcovati-2017-ccus-foundation` | `10.1182/blood-2017-01-763425` | Malcovati CCUS 2017 | Somatic-mutation interpretation in unexplained cytopenia, including CCUS identification and mutation-pattern risk for myeloid neoplasia. |
| `passamonti-2017-mysec-pm-secondary` | `10.1038/leu.2017.169` | MYSEC-PM Secondary Myelofibrosis Prognostic Model 2017 | MYSEC-PM clinical-molecular survival risk stratification for post-PV and post-ET myelofibrosis. |
| `tefferi-2020-mipss-et-pv` | `10.1111/bjh.16380` | MIPSS-ET/PV 2020 | Mutation-enhanced prognostic scoring for ET and PV, including survival, fibrotic progression, and leukemic-transformation associations. |
| `urrutia-2025-tp53-myeloid` | `10.1182/blood.2025029691` | Urrutia TP53 Myeloid Guide 2025 | Clinical TP53 allelic-state assessment in AML/MDS, including multi-hit definitions, testing interpretation, prognosis, and treatment implications. |

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

The human-readable table above describes corpus contents. Runtime evidence remains in the structured
`output/corpus/nel.corpus.json` and `output/corpus/nel.index.json` assets.
`output/corpus/blacklist.json` is retained only as a deprecated compatibility snapshot.

## Corpus user layer

Corpus contents are customised per user or per run through a corpus user layer
profile, which overlays the incorporated corpus without editing it. See
[`cul.md`](cul.md). The layer replaces the standalone
`output/corpus/blacklist.json`, which is now a deprecated fallback.

## Card browser

Build the browser with `python scripts/build_card_browser.py`. It reads
`output/corpus/` only, so it works in a release payload with no accepted
packages present. Pass `--full` in a source checkout to add the accepted evidence
block for each paper that has one, and `--cul <profile>` to load a profile for
editing. The generated file is written to `output/reports/card-browser.html`; the
compact release payload does not need to ship it for case execution.
