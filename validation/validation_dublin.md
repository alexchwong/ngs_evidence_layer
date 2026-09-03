# Validation Dublin

Ten synthetic cases designed to test the core functions expected of a molecular-haematology NGS report. Marking criteria are evaluator-only and must never be supplied to the report-generation workflow.

## Functional-test key

- **F1 — Diagnostic integration:** integrate molecular findings with the stated morphological/clinical diagnosis.
- **F2 — Diagnostic refinement:** refine or escalate the diagnosis when molecular findings require it.
- **F3 — Concurrent diagnosis:** identify a second/concurrent haematological diagnosis.
- **F4 — Prognosis:** provide clinically appropriate molecular prognostic interpretation.
- **F5 — Therapy:** identify a clinically relevant therapeutic target or treatment-defining molecular implication.
- **F6 — MRD:** identify the preferred established molecular MRD target when one is present.
- **F7 — Germline variant:** recognise a variant that should raise suspicion of germline origin.
- **F8 — Germline syndrome:** recognise the associated inherited predisposition syndrome.
- **F9 — Molecular prognostic framework:** correctly recognise and apply molecular variables within disease-specific prognostic systems, including IPSS-M, MIPSS70+/MIPSS70+ v2.0 and CPSS-Mol.

---

# Case 1

## Clinical information

46F presents with pancytopenia. Bone marrow examination shows acute myeloid leukaemia with 55% myeloblasts. Conventional cytogenetics demonstrates a normal karyotype.

She has had mild thrombocytopenia since her twenties. Her father also had longstanding thrombocytopenia and subsequently developed myelodysplastic syndrome.

Molecular testing identifies:

- NPM1 NM_002520.7:c.860_863dup p.(Trp288CysfsTer12), VAF 36%
- FLT3-ITD
- RUNX1 NM_001754.5:c.496C>T p.(Arg166Ter), VAF 48%

## NEL task

Integrate the molecular findings with AML classification and ELN 2022 risk, identify FLT3-directed actionability and the preferred molecular MRD target, and recognise the possible inherited RUNX1 predisposition without inferring germline origin from tumour-only sequencing.

## Marking criteria

#### R1 — Diagnosis and classification

- **R1C1 [F1].** Integrate the NPM1 and FLT3-ITD findings with the AML diagnosis rather than reporting them as isolated variant annotations.
- **R1C2 [F2].** Recognise AML with NPM1 mutation under the applicable WHO5/ICC classification framework.
- **R1C3 [F1/F8].** Do not allow the possible germline RUNX1 predisposition to obscure the classification of the current NPM1-mutated AML.

#### R2 — Prognostic interpretation

- **R2C1 [F4].** Under ELN 2022, recognise NPM1-mutated AML with FLT3-ITD as intermediate risk in the absence of an adverse-risk cytogenetic lesion; do not treat NPM1 mutation alone as automatically favourable.
- **R2C2 [F4/F7].** Do not use the RUNX1 variant as an acquired adverse-risk lesion without resolving its suspected constitutional origin; tumour-only VAF and family history support germline evaluation but do not prove origin.

#### R3 — Clinical actionability

- **R3C1 [F5].** Identify FLT3-ITD as therapeutically relevant and state the role of FLT3-directed therapy in the appropriate AML treatment setting.

#### R4 — MRD interpretation

- **R4C1 [F6].** Identify NPM1 as the preferred established molecular MRD target for this AML and prioritise it over FLT3-ITD.

#### R5 — Possible germline flagging

- **R5C1 [F7].** Recognise RUNX1 NM_001754.5:c.496C>T p.(Arg166Ter) at 48% VAF as suspicious for germline origin given the lifelong thrombocytopenia and compatible family history.
- **R5C2 [F8].** Raise RUNX1-associated familial platelet disorder with predisposition to myeloid malignancy and recommend constitutional confirmation/genetic assessment rather than declaring germline status from tumour-only sequencing.

---

# Case 2

## Clinical information

34M presents with bruising, anaemia, thrombocytopenia and disseminated intravascular coagulation. Bone marrow examination shows extensive infiltration by abnormal promyelocytes.

Molecular/cytogenetic testing demonstrates:

- PML::RARA fusion
- FLT3-ITD

## NEL task

Recognise PML::RARA-defined acute promyelocytic leukaemia, state its urgent treatment-defining implication, and identify the preferred disease-specific molecular MRD target without allowing FLT3-ITD to displace the defining fusion.

## Marking criteria

#### R1 — Diagnosis and classification

- **R1C1 [F1].** Integrate PML::RARA with the morphology and clinical presentation.
- **R1C2 [F2].** Identify acute promyelocytic leukaemia with PML::RARA.
- **R1C3 [F1].** Do not allow the co-occurring FLT3-ITD to displace PML::RARA as the disease-defining abnormality.

#### R2 — Prognostic interpretation

No case-specific criteria.

#### R3 — Clinical actionability

- **R3C1 [F5].** Recognise PML::RARA as immediately treatment-defining and state the appropriate APL-specific differentiation-therapy implication, including the urgency of ATRA when APL is suspected and ATRA/ATO-based treatment where appropriate.

#### R4 — MRD interpretation

- **R4C1 [F6].** Identify PML::RARA as the preferred established disease-specific molecular MRD target in APL and prioritise it over FLT3-ITD. Do not require the report to state that FLT3-ITD can never be used for MRD.

#### R5 — Possible germline flagging

No case-specific criteria.

---

# Case 3

## Clinical information

52F is diagnosed with acute myeloid leukaemia. Blast morphology and immunophenotype are compatible with core-binding-factor AML, and RUNX1::RUNX1T1 is demonstrated.

Separate from the blast population, the marrow contains multifocal dense aggregates of atypical spindle-shaped mast cells expressing tryptase and aberrant CD25.

Molecular testing identifies:

- RUNX1::RUNX1T1 fusion
- KIT NM_000222.3:c.2447A>T p.(Asp816Val), VAF 12%

## NEL task

Classify RUNX1::RUNX1T1 core-binding-factor AML, report its formal ELN risk and preferred molecular MRD target, and recognise the independently supported concurrent systemic mastocytosis without assigning KIT to the AML clone from bulk sequencing alone.

## Marking criteria

#### R1 — Diagnosis and classification

- **R1C1 [F1].** Integrate RUNX1::RUNX1T1 with the AML morphology.
- **R1C2 [F2].** Identify AML with RUNX1::RUNX1T1 / core-binding-factor AML.
- **R1C3 [F3].** Recognise that the independent dense atypical mast-cell infiltrate, aberrant mast-cell phenotype and KIT p.(Asp816Val) support concurrent systemic mastocytosis rather than assuming KIT belongs solely to the AML clone.
- **R1C4 [F1/F3].** Keep the AML and mastocytosis interpretations distinct while integrating both into the overall report.

#### R2 — Prognostic interpretation

- **R2C1 [F4].** Recognise the favourable ELN genetic-risk category of RUNX1::RUNX1T1 AML and that concurrent KIT mutation does not by itself change the formal ELN risk category; any discussion of KIT-associated relapse biology must not replace the formal risk assignment.

#### R3 — Clinical actionability

No case-specific criteria. Do not require treatment advice for the newly recognised concurrent mastocytosis.

#### R4 — MRD interpretation

- **R4C1 [F6].** Identify RUNX1::RUNX1T1 as the preferred established molecular MRD target for the AML and prioritise it over KIT p.(Asp816Val).

#### R5 — Possible germline flagging

No case-specific criteria.

---

# Case 4

## Clinical information

68M presents with progressive pancytopenia. Bone marrow examination shows a myelodysplastic neoplasm with increased blasts-1, with 8% marrow blasts.

His father developed MDS in his seventies and a paternal uncle developed AML.

Cytogenetic testing demonstrates del(17p) involving TP53.

Molecular testing identifies:

- TP53 NM_000546.6:c.743G>A p.(Arg248Gln), VAF 41%
- DDX41 NM_016222.4:c.415_418dup p.(Asp140delinsGlyTer), VAF 49%
- DDX41 NM_016222.4:c.1574G>A p.(Arg525His), VAF 7%

## NEL task

Integrate TP53 mutation plus del(17p) as multi-hit TP53 MDS biology and its adverse prognostic contribution, while separately recognising the possible inherited DDX41 predisposition and acquired second hit without declaring germline status or phasing from bulk sequencing.

## Marking criteria

#### R1 — Diagnosis and classification

- **R1C1 [F1].** Integrate the TP53 mutation and del(17p) with the MDS diagnosis.
- **R1C2 [F2].** Recognise biallelic/multi-hit TP53 involvement from a pathogenic TP53 mutation together with loss of the other TP53 locus through del(17p), using the applicable WHO5/ICC terminology.
- **R1C3 [F1/F8].** Keep the DDX41 predisposition architecture conceptually separate from the acquired TP53 allelic-state interpretation.

#### R2 — Prognostic interpretation

- **R2C1 [F4].** Recognise multi-hit TP53 as a major adverse prognostic finding in MDS.
- **R2C2 [F9].** Correctly recognise multi-hit TP53 as the major adverse TP53 molecular feature within IPSS-M; do not calculate a complete IPSS-M category unless all required variables are supplied.

#### R3 — Clinical actionability

No case-specific criteria.

#### R4 — MRD interpretation

No case-specific criteria.

#### R5 — Possible germline flagging

- **R5C1 [F7].** Recognise DDX41 NM_016222.4:c.415_418dup p.(Asp140delinsGlyTer) at 49% VAF, together with the family history, as strongly suspicious for germline origin.
- **R5C2 [F8].** Raise DDX41-associated germline predisposition to myeloid neoplasms and recommend constitutional confirmation/genetic assessment rather than declaring germline status from tumour-only sequencing.
- **R5C3 [F7/F8].** Recognise DDX41 NM_016222.4:c.1574G>A p.(Arg525His) at 7% VAF as compatible with an acquired second hit in the setting of an underlying germline DDX41 variant, while avoiding definitive phasing from bulk sequencing.

### Additional validation purpose

This is also the corpus-dependency demonstration case: the clinical stem should remain identical when testing the effect of removing versus restoring the literature required to support TP53 multi-hit interpretation from TP53 mutation plus del(17p).

---

# Case 5

## Clinical information

71F presents with macrocytic anaemia and thrombocytopenia. Bone marrow examination shows a low-blast myelodysplastic neoplasm with 3% marrow blasts and characteristic hypolobated megakaryocytes. Cytogenetic testing demonstrates an isolated del(5q).

A separate small population of abnormal mature B cells has hairy cytoplasmic projections and an immunophenotype supporting hairy-cell leukaemia.

Molecular testing identifies:

- SF3B1 NM_012433.4:c.2098A>G p.(Lys700Glu), VAF 31%
- BRAF NM_004333.6:c.1799T>A p.(Val600Glu), VAF 5%

## NEL task

Resolve the del(5q)/SF3B1 MDS classification and molecular prognostic implications, and report the separately supported concurrent hairy-cell leukaemia without attributing BRAF p.(Val600Glu) to the myeloid clone or IPSS-M assessment.

## Marking criteria

#### R1 — Diagnosis and classification

- **R1C1 [F1].** Integrate del(5q) and SF3B1 p.(Lys700Glu) with the MDS phenotype.
- **R1C2 [F2].** Correctly resolve the del(5q)/SF3B1 classification interaction: the isolated del(5q) abnormality is not overridden merely because SF3B1 is mutated; in ICC, isolated del(5q) excludes assignment to the SF3B1-mutated MDS entity.
- **R1C3 [F3].** Recognise that BRAF p.(Val600Glu), together with the separate characteristic B-cell population, supports concurrent hairy-cell leukaemia.
- **R1C4 [F3].** Do not attribute BRAF p.(Val600Glu) to the MDS simply because both abnormalities were detected on the same molecular assay.

#### R2 — Prognostic interpretation

- **R2C1 [F4].** Provide the prognostic interpretation of the MDS component independently of the concurrent hairy-cell leukaemia.
- **R2C2 [F9].** Recognise SF3B1 mutation as a favourable molecular variable within IPSS-M, interpreted in the context of the complete MDS profile rather than as a stand-alone risk assignment.
- **R2C3 [F9].** Do not use BRAF p.(Val600Glu) from the separate lymphoid neoplasm as an IPSS-M variable.

#### R3 — Clinical actionability

No case-specific criteria. Do not require treatment advice for the newly recognised concurrent hairy-cell leukaemia.

#### R4 — MRD interpretation

No case-specific criteria.

#### R5 — Possible germline flagging

No case-specific criteria.

---

# Case 6

## Clinical information

58M has established primary myelofibrosis with splenomegaly, anaemia and constitutional symptoms.

Molecular testing identifies:

- CALR NM_004343.4:c.1099_1150del p.(Leu367ThrfsTer46), VAF 42%
- ASXL1 NM_015338.6:c.1934dup p.(Gly646TrpfsTer12), VAF 28%
- U2AF1 NM_006758.3:c.470A>C p.(Gln157Pro), VAF 19%

## NEL task

Integrate the variants with established primary myelofibrosis and provide balanced disease-specific molecular prognostic interpretation, accounting for favourable CALR type-1 biology and the adverse ASXL1 and U2AF1 Q157 features in the relevant MIPSS70 frameworks.

## Marking criteria

#### R1 — Diagnosis and classification

- **R1C1 [F1].** Integrate the detected variants with the established primary myelofibrosis diagnosis.

#### R2 — Prognostic interpretation

- **R2C1 [F4].** Provide molecular prognostic interpretation rather than treating the canonical driver mutation alone as sufficient.
- **R2C2 [F9].** Recognise CALR type-1/type-1-like biology as a favourable molecular feature in the relevant PMF prognostic framework.
- **R2C3 [F9].** Recognise ASXL1 mutation as an adverse/high-molecular-risk feature.
- **R2C4 [F9].** Recognise U2AF1 Q157 mutation as an adverse molecular feature in the appropriate MIPSS70+/MIPSS70+ v2.0 context.
- **R2C5 [F4/F9].** Do not label the patient molecularly favourable solely because CALR type 1 is present; the adverse co-mutations must also influence the interpretation.

#### R3 — Clinical actionability

No case-specific criteria.

#### R4 — MRD interpretation

No case-specific criteria.

#### R5 — Possible germline flagging

No case-specific criteria.

---

# Case 7

## Clinical information

29F presents with persistent cytopenias. She has longstanding monocytopenia, recurrent severe viral warts and a previous atypical mycobacterial infection. Her mother developed MDS at 43 years of age.

Bone marrow examination demonstrates a myelodysplastic neoplasm with increased blasts-1, with 7% marrow blasts. Cytogenetic testing demonstrates monosomy 7.

Molecular testing identifies:

- GATA2 NM_032638.5:c.1061C>T p.(Thr354Met), VAF 48%
- ASXL1 NM_015338.6:c.1934dup p.(Gly646TrpfsTer12), VAF 21%

## NEL task

Integrate the acquired MDS findings and their molecular prognostic contribution while recognising the phenotype and GATA2 variant as suspicious for GATA2-associated germline predisposition, requiring constitutional confirmation rather than tumour-panel inference.

## Marking criteria

#### R1 — Diagnosis and classification

- **R1C1 [F1].** Integrate the molecular findings, monosomy 7 and characteristic clinical phenotype with the MDS diagnosis.
- **R1C2 [F1/F8].** Distinguish the underlying germline predisposition syndrome from the acquired MDS while recognising that they are clinically related.

#### R2 — Prognostic interpretation

- **R2C1 [F4].** Recognise the adverse implications of the acquired MDS abnormalities.
- **R2C2 [F9].** Correctly recognise the adverse acquired molecular contribution of ASXL1 within an IPSS-M assessment and interpret it alongside the supplied cytogenetic abnormality; do not calculate a complete IPSS-M category unless all required variables are supplied.
- **R2C3 [F7/F9].** Do not automatically treat the likely constitutional GATA2 variant as an acquired IPSS-M mutation.

#### R3 — Clinical actionability

No case-specific criteria.

#### R4 — MRD interpretation

No case-specific criteria.

#### R5 — Possible germline flagging

- **R5C1 [F7].** Recognise GATA2 NM_032638.5:c.1061C>T p.(Thr354Met) as suspicious for germline origin based on the near-heterozygous VAF, young age, characteristic phenotype and family history.
- **R5C2 [F8].** Recognise GATA2 deficiency / GATA2-associated germline predisposition to myeloid malignancy.
- **R5C3 [F8].** Recommend constitutional confirmation/genetic assessment rather than assuming germline status from tumour-panel sequencing alone.

---

# Case 8

## Clinical information

73M has persistent absolute and relative monocytosis, splenomegaly and bone-marrow dysplasia consistent with chronic myelomonocytic leukaemia. He also has an IgM paraprotein. Bone marrow examination demonstrates a separate small clonal lymphoplasmacytic B-cell population.

Molecular testing identifies:

- ASXL1 NM_015338.6:c.1934dup p.(Gly646TrpfsTer12), VAF 39%
- NRAS NM_002524.5:c.35G>A p.(Gly12Asp), VAF 18%
- MYD88 NM_002468.4:c.794T>C p.(Leu265Pro), VAF 7%

## NEL task

Interpret ASXL1 and NRAS within the established CMML and its CPSS-Mol assessment, while recognising the independently supported concurrent lymphoplasmacytic neoplasm and excluding its MYD88 finding from the CMML clone and prognostic score.

## Marking criteria

#### R1 — Diagnosis and classification

- **R1C1 [F1].** Integrate ASXL1 and NRAS with the established CMML diagnosis.
- **R1C2 [F3].** Recognise that MYD88 p.(Leu265Pro), together with the IgM paraprotein and independent lymphoplasmacytic clone, supports a concurrent lymphoplasmacytic neoplasm / Waldenström macroglobulinaemia when the full diagnostic criteria are met.
- **R1C3 [F3].** Do not force MYD88 p.(Leu265Pro) into the CMML molecular profile.
- **R1C4 [F1/F3].** Keep the myeloid and lymphoid disease interpretations distinct while integrating both into the final report.

#### R2 — Prognostic interpretation

- **R2C1 [F4].** Provide the appropriate molecular prognostic assessment of the CMML component.
- **R2C2 [F9].** Recognise ASXL1 and NRAS as adverse molecular variables used by CPSS-Mol.
- **R2C3 [F9].** Apply CPSS-Mol only to the CMML component and do not use MYD88 from the separate lymphoid clone in the CMML score.

#### R3 — Clinical actionability

No case-specific criteria. Do not require treatment advice for the newly recognised concurrent lymphoplasmacytic neoplasm.

#### R4 — MRD interpretation

No case-specific criteria.

#### R5 — Possible germline flagging

No case-specific criteria.

---

# Case 9

## Clinical information

71M presents with fatigue and recurrent infections and is not fit for intensive chemotherapy because of ECOG 2 and cardiac comorbidity. Hb 82 g/L, WCC 3.2 x10^9/L, ANC 0.7 x10^9/L and platelets 60 x10^9/L. The film shows 24% circulating blasts and no Auer rods. Bone marrow shows 46% blasts and no dysplastic ring sideroblasts. Karyotype is normal. Marrow morphological diagnosis: acute myeloid leukaemia.

Molecular testing identifies:

- IDH2 NM_002168.4:c.515G>A p.(Arg172Lys), VAF 40%
- SRSF2 NM_003016.4:c.284C>A p.(Pro95His), VAF 36%

Cytogenetics: 46,XY[20].

## NEL task

Classify AML with myelodysplasia-related molecular biology, distinguish the entity-defining SRSF2 finding from actionable IDH2 p.(Arg172Lys), and report the materially different ELN 2022 and ELN 2024 Less-Intensive risk categories in their treatment contexts.

## Marking criteria

#### R1 — Diagnosis and classification

- **R1C1 [F1/F2].** State the WHO5 diagnosis as AML, myelodysplasia-related because SRSF2 is an MR-defining mutation; IDH2 p.(Arg172Lys) is not entity-defining.
- **R1C2 [F1].** Show the reasoning that SRSF2 establishes myelodysplasia-related molecular biology while IDH2 is therapeutically relevant but does not define the AML entity.
- **R1C3 [F1].** Interpret the similar VAFs cautiously: bulk VAF does not establish founding/subclonal order or prove an antecedent clone.

#### R2 — Prognostic interpretation

- **R2C1 [F4].** Report both materially different applicable categories: ELN 2022 adverse and ELN 2024 Less-Intensive favourable; either may be presented first.
- **R2C2 [F4].** Explain that SRSF2 drives the ELN 2022 adverse assignment and IDH2 p.(Arg172Lys) drives the ELN 2024 less-intensive favourable assignment in the relevant treatment context.

#### R3 — Clinical actionability

- **R3C1 [F5].** Identify IDH2 p.(Arg172Lys) as a therapeutically actionable mutation and state the role of an IDH2-directed inhibitor such as enasidenib in an approved or trial setting appropriate to jurisdiction and disease phase.

#### R4 — MRD interpretation

No case-specific criteria. This suite does not use negative MRD tests.

#### R5 — Possible germline flagging

No case-specific criteria.

---

# Case 10

## Clinical information

68M presents with pancytopenia and fatigue. Hb 84 g/L, MCV 98 fL, WCC 2.1 x10^9/L, ANC 0.9 x10^9/L and platelets 41 x10^9/L. Film shows occasional blasts and dysplastic neutrophils. Bone marrow demonstrates trilineage dysplasia with 4% blasts. No 17p loss or copy-neutral loss of heterozygosity is detected. Marrow morphological diagnosis: myelodysplastic neoplasm with low blasts and multilineage dysplasia.

Molecular testing identifies:

- TP53 NM_000546.6:c.524G>A p.(Arg175His), VAF 12%

Cytogenetics: 46,XY[20]; FISH negative for 17p deletion.

## NEL task

Retain the supported low-blast MDS classification, distinguish a single monoallelic TP53 mutation from TP53 multi-hit disease, and describe only the supported IPSS-M molecular contribution without inferring an unobserved second hit or calculating an incomplete score.

## Marking criteria

#### R1 — Diagnosis and classification

- **R1C1 [F1/F2].** Do not diagnose MDS with biallelic TP53 inactivation / TP53 multi-hit disease: only one TP53 mutation is detected, VAF is 12%, and there is no 17p loss or cnLOH. Retain the morphology-based low-blast MDS classification under the applicable framework.
- **R1C2 [F2].** State that a single TP53 mutation at 12% VAF with negative second-hit testing does not establish biallelic/multi-hit TP53 involvement and is not equivalent to the multi-hit case.
- **R1C3 [F1].** Do not infer a second TP53 hit from VAF alone.

#### R2 — Prognostic interpretation

- **R2C1 [F4/F9].** Recognise that a single monoallelic TP53 mutation does not confer the major adverse TP53-multihit contribution used by IPSS-M; do not calculate a complete IPSS-M category unless all required variables are supplied.
- **R2C2 [F9].** Explicitly distinguish single-hit TP53 from TP53 multi-hit when describing the molecular risk contribution.

#### R3 — Clinical actionability

No case-specific criteria.

#### R4 — MRD interpretation

No case-specific criteria. This suite does not use negative MRD tests.

#### R5 — Possible germline flagging

No case-specific criteria.

---

# Source notes

## Functional coverage

| Functional test | Dublin cases |
| --- | --- |
| F1 Diagnostic integration | 1–10 |
| F2 Diagnostic refinement | 1, 2, 3, 4, 5, 9, 10 |
| F3 Concurrent diagnosis | 3, 5, 8 |
| F4 Prognosis | 1, 3, 4, 5, 6, 7, 8, 9, 10 |
| F5 Therapy | 1, 2, 9 |
| F6 Preferred molecular MRD target | 1, 2, 3 |
| F7 Potential germline variant | 1, 4, 7 |
| F8 Germline syndrome | 1, 4, 7 |
| F9 Molecular prognostic framework | 4, 5, 6, 7, 8, 10 |
