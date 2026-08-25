# NEL brief validation set — consolidated clinical regression suite

## Purpose

This 10-case suite consolidates the highest-yield behavioural tests from the general and function-targeted validation sets into fewer end-to-end clinical regression cases.

NEL is asked to explain how supplied clinicomorphological information and molecular findings confirm, change, exclude or qualify diagnosis, prognosis, actionability, MRD interpretation and possible germline predisposition. Marking criteria are evaluator-only and must not be supplied to NEL before `report-final.md` is complete.

## Design conventions

- WHO-5 is primary. ICC is reported when it produces a materially different classification.
- Molecular findings must not replace missing clinicopathological criteria unless the classification explicitly permits molecular definition at the supplied blast threshold.
- Bulk tumour VAF must not be used to infer germline status, phase, mutation order, shared clonality or an unobserved second hit.
- Complete prognostic scores are not required when necessary inputs are absent; report only supported molecular contributions or limitations.
- Disease-specific treatment and MRD claims must remain specific to the supplied disease, alteration and clinical setting.

---

# Case 1 — NPM1-mutated AML arising from an MDS-range presentation

## Clinical information

Cytopenias and marrow dysplasia are present. Marrow blasts are 12%. Provisional diagnosis: **myelodysplastic neoplasm with increased blasts-2 (MDS-IB2)**.

**NGS:** `NPM1` type A, NM_002520.7:c.860_863dup, p.(Trp288CysfsTer12), VAF 38%; `FLT3` NM_004119.3:c.2503G>T, p.(Asp835Tyr), VAF 24%.

**Cytogenetics:** Normal.

## NEL task

Recognise molecular escalation from the provisional MDS diagnosis to NPM1-mutated AML, apply the WHO-5/ICC blast-threshold rules and ELN risk category, report the FLT3-TKD treatment implication, and select the preferred molecular MRD target.

## Marking criteria

- **R1C1:** Refine the WHO-5 diagnosis to **AML with mutated NPM1** despite the 12% marrow blast count; the NPM1-defined WHO-5 entity is not restricted by the conventional 20% blast threshold.
- **R1C2:** State the corresponding ICC **AML with mutated NPM1** because the supplied 12% blast count exceeds the ICC minimum for this entity.
- **R2C1:** Assign **ELN 2022 favourable risk** in the supplied setting without an adverse-risk defining finding; FLT3-TKD does not displace the NPM1 favourable-risk assignment.
- **R3C1:** State that FLT3 D835Y is an actionable FLT3-TKD alteration in the appropriate AML treatment setting, with treatment phase and approval/access qualified where relevant.
- **R4C1:** Identify the exact NPM1 type A mutation as the preferred dedicated high-sensitivity molecular MRD target.

---

# Case 2 — AML with myelodysplasia-related and clonal-haematopoiesis-associated mutations

## Clinical information

Pancytopenia. Marrow shows 30% myeloid blasts. Provisional diagnosis: **acute myeloid leukaemia (AML)**.

**NGS:** `SRSF2` NM_003016.5:c.284C>A, p.(Pro95His), VAF 41%; `ASXL1` NM_015338.6:c.1934dup, p.(Gly646TrpfsTer12), VAF 34%; `DNMT3A` NM_022552.5:c.2645G>A, p.(Arg882His), VAF 39%; `TET2` NM_001127208.3:c.1132_1133del, p.(Gly378CysfsTer11), VAF 45%.

**Cytogenetics:** Normal.

## NEL task

Recognise AML with myelodysplasia-related gene mutations, distinguish the qualifying lesions from common clonal-haematopoiesis-associated mutations, apply ELN 2022, and avoid promoting these mutations to stand-alone AML MRD markers.

## Marking criteria

- **R1C1:** State **AML, myelodysplasia-related** on the basis of qualifying myelodysplasia-related gene mutation(s), including SRSF2 and ASXL1.
- **R1C2:** Do not describe DNMT3A or TET2 as the lesions that establish the AML-MR entity; they support clonality but are not the qualifying AML-MR gene mutations in this case.
- **R2C1:** Assign **ELN 2022 adverse risk** because of the qualifying myelodysplasia-related gene mutation(s).
- **R4C1:** Do not treat SRSF2, ASXL1, DNMT3A or TET2 as validated stand-alone AML MRD markers.

---

# Case 3 — Isolated FLT3-ITD AML

## Clinical information

Pancytopenia. Marrow shows 30% myeloid blasts. Provisional diagnosis: **acute myeloid leukaemia (AML)**.

**NGS:** `FLT3` internal tandem duplication, NM_004119.3:c.1773_1793dup, VAF 32%.

**Cytogenetics:** Normal.

No adverse-risk defining lesion is supplied.

## NEL task

Preserve AML, apply the current ELN interpretation of isolated FLT3-ITD without using allelic ratio, report disease-specific treatment actionability, and state the AML MRD role and limitations of FLT3-ITD.

## Marking criteria

- **R1C1:** Preserve **AML**. FLT3-ITD does not independently define a different WHO-5 AML entity.
- **R2C1:** Assign **ELN 2022 intermediate risk** in the absence of an adverse-risk lesion; do not use FLT3-ITD allelic ratio for ELN 2022 risk assignment.
- **R3C1:** Report FLT3-mutated AML as therapeutically actionable, with the treatment setting qualified.
- **R4C1:** Recognise FLT3-ITD as a validated high-sensitivity molecular MRD target in AML while respecting timepoint/assay-specific guidance and limitations of using it as the sole follow-up marker.

---

# Case 4 — PML::RARA-positive acute promyelocytic leukaemia

## Clinical information

Pancytopenia. Marrow shows 30% abnormal promyelocytes/blasts. Provisional diagnosis: **acute myeloid leukaemia (AML)**.

**FISH:** `PML::RARA` rearrangement positive.

**NGS:** `FLT3` internal tandem duplication, NM_004119.3:c.1773_1793dup, VAF 32%; `KRAS` NM_004985.5:c.35G>A, p.(Gly12Asp), VAF 4%.

## NEL task

Integrate the defining non-NGS fusion result, apply diagnostic precedence, report its immediate disease-specific treatment significance, and prioritise the correct MRD marker over secondary NGS variants.

## Marking criteria

- **R1C1:** Refine the diagnosis to **acute promyelocytic leukaemia with PML::RARA**. PML::RARA takes diagnostic precedence over FLT3-ITD and low-level KRAS.
- **R3C1:** Recognise that PML::RARA has an immediate disease-specific treatment implication even though it was detected outside the NGS assay.
- **R4C1:** Identify `PML::RARA` as the preferred leukaemia-specific molecular follow-up target; FLT3-ITD or KRAS must not replace it as the principal MRD marker.

---

# Case 5 — Single bZIP CEBPA mutation

## Clinical information

Pancytopenia. Marrow shows 30% myeloid blasts. Provisional diagnosis: **acute myeloid leukaemia (AML)**.

**NGS:** `CEBPA` **bZIP in-frame** mutation NM_004364.5:c.937_939dup, p.(Lys313dup), VAF 37%.

**Cytogenetics:** Normal.

No second pathogenic `CEBPA` variant is detected.

## NEL task

Recognise that a single explicitly in-frame bZIP CEBPA mutation is sufficient for the CEBPA-defined AML entity and favourable ELN category, without requiring biallelic CEBPA mutation or inventing a routine stand-alone molecular MRD strategy.

## Marking criteria

- **R1C1:** State **AML with CEBPA mutation / bZIP in-frame CEBPA-mutated AML**. A second CEBPA mutation is not required when the single mutation is explicitly an in-frame bZIP mutation.
- **R2C1:** Assign **ELN 2022 favourable risk** on the basis of the in-frame bZIP CEBPA mutation in the supplied setting.
- **R4C1:** Do not present routine detection/clearance of this CEBPA variant as an established stand-alone molecular MRD strategy.

---

# Case 6 — High-blast MDS with SF3B1 and adverse IPSS-M contributors

## Clinical information

Cytopenias and marrow dysplasia are present. Marrow blasts are 12%. Provisional diagnosis: **myelodysplastic neoplasm with increased blasts-2 (MDS-IB2)**.

**NGS:** `SF3B1` NM_012433.4:c.1998G>T, p.(Lys666Asn), VAF 37%; `EZH2` NM_004456.5:c.862C>T, p.(Arg288Ter), VAF 28%; `CBL` NM_005188.4:c.1111T>C, p.(Tyr371His), VAF 31%.

**Cytogenetics:** Normal.

## NEL task

Respect the high-blast WHO-5 diagnosis rather than allowing SF3B1 to force a low-blast entity, report the materially different ICC classification, and describe the mixed molecular prognostic contributions without constructing an incomplete IPSS-M score.

## Marking criteria

- **R1C1:** State **WHO-5 MDS-IB2**, not MDS with low blasts and SF3B1 mutation, because the supplied 12% marrow blasts preclude the low-blast SF3B1-defined entity.
- **R1C2:** State the materially different ICC **MDS/AML with myelodysplasia-related gene mutation(s)**; SF3B1 and EZH2 are qualifying myelodysplasia-related genes in this blast range.
- **R2C1:** Recognise the favourable SF3B1 molecular contribution and adverse CBL/EZH2 contributions within IPSS-M rather than assigning all detected genes the same direction of effect.
- **R2C2:** Do not fabricate a complete IPSS-M category when all required non-molecular inputs are not supplied.

---

# Case 7 — MDS with mutation-plus-deletion TP53 architecture

## Clinical information

Cytopenias and marrow dysplasia are present. Marrow blasts are 12%. Provisional diagnosis: **myelodysplastic neoplasm with increased blasts-2 (MDS-IB2)**.

The NGS assay is tumour-only. No constitutional specimen has been tested.

**NGS:** `TP53` NM_000546.6:c.743G>A, p.(Arg248Gln), VAF 48%.

**Cytogenetics/FISH:** del(17p) involving `TP53`.

## NEL task

Integrate the observed TP53 mutation and cytogenetic second hit, apply the materially different WHO-5 and ICC classifications and adverse molecular interpretation, while avoiding an unsupported germline inference from tumour VAF.

## Marking criteria

- **R1C1:** State **WHO-5 MDS with biallelic TP53 inactivation** because the TP53 mutation plus deletion of the TP53 locus establishes a multi-hit/biallelic architecture.
- **R1C2:** State the materially different ICC entity **MDS/AML with mutated TP53**.
- **R2C1:** Report TP53 multi-hit status as the dominant adverse molecular feature as per IPSS-M.
- **R5C1:** Do not infer constitutional TP53 status from the approximately 50% tumour-only VAF; germline status remains unestablished unless separately confirmed.

---

# Case 8 — BCR::ABL1-positive AML-range presentation with an ANKRD26 germline flag

## Clinical information

Pancytopenia. Marrow shows 30% myeloid blasts. Provisional diagnosis: **acute myeloid leukaemia (AML)**.

No previous diagnosis of CML is documented. Historical blood counts before the acute presentation are not available.

The patient's father was said to have had mildly low platelet counts for many years and was later treated for a myelodysplastic neoplasm in his seventies; no genetic testing information is available.

The NGS assay is tumour-only. No constitutional specimen has been tested.

**Fusion testing:** `BCR::ABL1` e13a2 (b2a2), p210 transcript detected.

**NGS:** `ANKRD26` NM_014915.3:c.-128G>A, VAF 51%. No other pathogenic or likely pathogenic SNV/short-indel finding is detected.

## NEL task

Recognise the BCR::ABL1-positive AML-range presentation while retaining CML blast phase as an important competing diagnosis requiring historical correlation. Independently recognise the characteristic ANKRD26 5′ UTR germline-predisposition signal and subtle family history without allowing tumour-only VAF to establish constitutional status.

## Marking criteria

- **R1C1:** State that the current 30% blast presentation with BCR::ABL1 satisfies the blast requirement for **AML with BCR::ABL1** if this represents de novo AML.
- **R1C2:** Explicitly report **possible CML blast phase** and recommend correlation with historical blood counts and prior evidence of chronic-phase CML; the BCR::ABL1 fusion alone must not be treated as proof of de novo AML.
- **R1C3:** Do not downgrade the significance of BCR::ABL1 because routine SNV/indel testing did not identify an acquired AML-defining mutation; the fusion was established by separate testing.
- **R5C1:** Flag **suspected/possible germline ANKRD26 predisposition**, recognising the characteristic 5′ UTR variant architecture together with the family history; do not call the tumour-only 51% VAF definitively constitutional.
- **R5C2:** State that confirmed germline ANKRD26 predisposition is relevant to inherited platelet disorder/myeloid-neoplasm predisposition and recommend constitutional confirmation using an appropriate non-haematopoietic specimen with genetic counselling; family/donor implications remain conditional pending confirmation.

---

# Case 9 — Proliferative CMML/MPN differential with a RAS-pathway-heavy genotype

## Clinical information

Leukocytosis and splenomegaly are present. WCC is 15.0 × 10^9/L. Monocytes are 2.25 × 10^9/L and 15% of the WCC on repeated measurements over 4 months. Reactive causes of monocytosis have been excluded.

A marrow aspirate is haemodilute and the trephine is insufficient for definitive morphological classification. Provisional diagnostic context: **MDS/MPN or MPN under evaluation, with CMML in the differential**. Relevant fusion/rearrangement exclusion testing is still pending.

**NGS:** `SRSF2` NM_003016.5:c.284C>A, p.(Pro95His), VAF 42%; `TET2` NM_001127208.3:c.1132_1133del, p.(Gly378CysfsTer11), VAF 45%; `NRAS` NM_002524.5:c.35G>A, p.(Gly12Asp), VAF 18%; `CBL` NM_005188.4:c.1111T>C, p.(Tyr371His), VAF 24%; `PTPN11` NM_002834.5:c.226G>A, p.(Glu76Lys), VAF 11%; `NF1` NM_001042492.3:c.2041C>T, p.(Arg681Ter), VAF 16%.

## NEL task

Use the persistent qualifying monocytosis and clonal, RAS-pathway-heavy genotype to identify CMML as the leading diagnostic consideration while respecting missing marrow/exclusion information. Recognise the proliferative context without treating the signalling mutations as independently diagnostic or importing disease-specific prognostic frameworks before the disease is established.

## Marking criteria

- **R1C1:** State that the persistent absolute and relative monocytosis plus clonal findings make **CMML a leading/major diagnostic consideration**, but do not present the diagnosis as fully established while required clinicopathological classification/exclusion information remains incomplete.
- **R1C2:** State that SRSF2/TET2 support a clonal myeloid process and that the NRAS/CBL/PTPN11/NF1 RAS-pathway genotype supports proliferative biology; none of these mutations independently establishes CMML or a canonical MPN diagnosis.
- **R1C3:** Recognise the **proliferative CMML context** from WCC >13 × 10^9/L if discussing CMML phenotype, but do not invent a blast-based subgroup when reliable marrow/blast information is unavailable.
- **R2C1:** Do not apply PMF-specific, MDS-specific or other disease-specific prognostic interpretation merely because individual detected genes occur in those frameworks before the final disease context is established.

---

# Case 10 — Borderline non-MDS cytopenia with DDX41 second-event architecture

## Clinical information

Persistent pancytopenia. Marrow shows mild/borderline trilineage dysplasia that is insufficient for a morphological diagnosis of MDS. Blasts are not increased. Provisional diagnosis: **CCUS**.

The patient is 68 years old. The patient's father developed MDS at age 71 and a paternal aunt developed AML at age 66.

The NGS assay is tumour-only. No constitutional specimen has been tested.

**NGS:** `DDX41` NM_016222.4:c.415_418dup, p.(Asp140GlyfsTer2), VAF 48%; `DDX41` NM_016222.4:c.1574G>A, p.(Arg525His), VAF 9%.

**Cytogenetics:** Normal.

## NEL task

Preserve the non-MDS clinicomorphological boundary, recognise possible germline DDX41 predisposition and the characteristic lower-VAF second-event architecture, and avoid unsupported phase, clonality or constitutional claims from bulk tumour sequencing.

## Marking criteria

- **R1C1:** Do not upgrade the borderline marrow findings to MDS. The lower-VAF DDX41 R525H provides an acquired clonal marker compatible with CCUS in the supplied cytopenic non-MDS context, while the near-heterozygous truncating DDX41 variant remains potentially constitutional.
- **R5C1:** Report **suspected/possible germline DDX41 predisposition** based on the loss-of-function variant, lower-VAF recurrent DDX41 second-event architecture and family history; VAF alone is insufficient.
- **R5C2:** Do not state that the two DDX41 variants are proven to be in trans, on different clones, or that the 48% allele is definitively constitutional from bulk tumour sequencing.
- **R5C3:** Recommend constitutional confirmation using an appropriate non-haematopoietic specimen and genetic counselling, with donor/family implications expressed conditionally pending confirmation.
