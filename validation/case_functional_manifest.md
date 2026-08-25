# Functional validation manifest

## Purpose and access rule

This manifest is a developer/evaluator index for `validation/case_functional.md`. It describes the reporting function intentionally isolated by each case.

**This file is never a model input during `nel-validate-function`.** It must not be read before or during report generation and is not included in the external marking ZIP. The selected clinical case is retrieved deterministically from `case_functional.md`; marking criteria are embedded only after `report-final.md` is complete.

| Case | Scenario | Reporting function under test |
|---|---|---|
| 1A | AML; DNMT3A + TET2 only | Preserve AML; distinguish CH-associated variants from AML-defining/AML-MR lesions; avoid invalid MRD use. |
| 1B | AML; SRSF2 + ASXL1 + TET2 | Escalate to AML-MR from qualifying MR-gene mutations and apply adverse AML risk. |
| 1C | AML; FLT3-ITD | Separate diagnosis from FLT3-ITD prognosis, treatment actionability and validated MRD use. |
| 1D | AML; PML::RARA plus secondary FLT3/KRAS | Apply defining-abnormality precedence; integrate treatment implication; choose PML::RARA as principal MRD marker. |
| 1E | AML-range blasts; BCR::ABL1; no history | Report de novo AML-with-BCR::ABL1 possibility while explicitly flagging possible CML blast phase and need for historical counts. |
| 1F | AML; one TP53 mutation; cytogenetics pending | Report ICC TP53 entity/adverse biology while keeping allelic state unresolved. |
| 1G | AML; TP53 mutation + 17p deletion | Recognise mutation-plus-locus-loss as multi-hit/biallelic TP53 architecture. |
| 1H | AML; one explicitly labelled bZIP in-frame CEBPA mutation | Recognise that one bZIP in-frame mutation is sufficient; do not require biallelic CEBPA; apply favourable ELN risk. |
| 2A | MDS-IB2; no variants; cytogenetics pending | Preserve morphologic disease after negative NGS; retain classification/prognostic limits from pending cytogenetics. |
| 2B | MDS-IB2; DNMT3A + TET2 only | Distinguish clonality/CH-associated variants from entity-defining molecular escalation. |
| 2C | MDS stem; NPM1 type A | Escalate 12%-blast MDS presentation to NPM1-mutated AML and identify NPM1 MRD role. |
| 2D | MDS; one TP53 mutation at 55% | Prevent VAF-only conversion into definitive biallelic or germline status; preserve WHO/ICC distinction. |
| 2E | MDS; two TP53 mutations | Recognise two-mutation multi-hit TP53 architecture and its classification/prognostic consequences. |
| 2F | MDS; RUNX1 truncation; lifelong platelet phenotype/family history | Generate clinically warranted possible-germline RUNX1 wording, constitutional-testing and family/donor implications without tumour-only overclaim. |
| 2G | MDS; near-heterozygous DDX41 LoF + low-VAF R525H + family history | Recognise characteristic possible-germline/second-event architecture while avoiding phase and constitutional-allele assumptions. |
| 3A | Platelets 700, WCC 14; no marrow; no mutations | Do not exclude or diagnose MPN from a negative panel; preserve need for marrow classification. |
| 3B | Same stem; CALR type 1 | Use CALR as MPN support without overcalling ET versus PMF in the absence of marrow. |
| 3C | Same stem; JAK2 V617F 15% | Benchmark lower-VAF association as more ET-compatible while forbidding diagnosis/zygosity inference from VAF alone. **Known current corpus gap:** ET-versus-PMF VAF association is not yet represented. |
| 3D | Same stem; JAK2 V617F 80% | Benchmark high-VAF association as more PMF-compatible while forbidding diagnosis/zygosity inference from VAF alone. **Known current corpus gap:** ET-versus-PMF VAF association is not yet represented. |
| 3E | Same stem; IDH1 R132H only | Report clonality without treating IDH1 as a canonical MPN driver or importing PMF-specific prognosis before diagnosis. |
| 3F | Same stem; NRAS + ASXL1 + persistent monocytosis | Surface CMML as a major competing diagnosis from clinical monocytosis plus clonality, without genotype-only diagnosis or invented marrow/blast classification. |
| 3G | Same stem; lifelong familial thrombocytosis; MPL S505N | Recognise possible hereditary MPL thrombocytosis and germline testing need; do not equate MPL/VAF with acquired ET/PMF or definitive germline status. |
| 4A | KIT D816V/systemic mastocytosis | Low-VAF disease-supporting hotspot integrated with strong clinicomorphology. |
| 4B | CSF3R T618I/CNL | Strong molecular support used with, not instead of, clinicopathological criteria. |
| 4C | BRAF V600E/hairy cell leukaemia | Strong supportive hotspot integrated with blood/flow findings while pathology is pending. |
| 4D | MYD88 L265P/LPL-WM | Supportive but non-specific hotspot integrated with IgM/lymphoplasmacytic context. |
