# NEL-focused case set — clinician-authored validation set

## Purpose

These cases test whether the NGS Evidence Layer (NEL) correctly explains how an NGS result **confirms, changes, excludes or qualifies an explicitly supplied clinicomorphological diagnosis**, and how the result affects prognosis, actionability, MRD interpretation or possible germline predisposition.

NEL is not asked to derive a morphological diagnosis from molecular findings alone or to supply missing clinicopathological criteria.

## Design conventions

- Each case supplies an explicit provisional clinicomorphological diagnosis or diagnostic context.
- Marking criteria are grounded in the R1–R5 framework in `rules/agreed_reporting_rules.md`.
- WHO-5 is primary. ICC is required when it produces a materially different entity.
- Complete prognostic scores are not required unless every necessary input is supplied. Otherwise, report the molecular contribution or limitation.
- Bulk VAF does not establish mutation order, phase, shared clonality or germline status.
- Tumour-only sequencing must not be used to assign definitive germline status.
- Case information includes negative findings only when they aid interpretation.
- A factually correct negative statement in the candidate report is neutral even when unnecessary. It does not lower the marking category unless it is false, contradicts supplied case information, or materially contributes to an incorrect interpretation.

---

# Case 1 — AML with contrasting molecular findings

## Shared stem

Pancytopenia. Marrow shows 30% myeloid blasts. Provisional diagnosis: **acute myeloid leukaemia (AML)**.

## Case 1A — DNMT3A/TET2-mutated AML

### Clinical information

**NGS:** `DNMT3A` NM_022552.5:c.2645G>A, p.(Arg882His), VAF 42%; `TET2` NM_001127208.3:c.1132_1133del, p.(Gly378CysfsTer11), VAF 36%.

**Cytogenetics:** Normal.

### NEL task

Preserve the supplied AML diagnosis, distinguish these clonal-haematopoiesis-associated mutations from AML-defining or myelodysplasia-related defining lesions, apply the appropriate AML prognostic framework, and identify the limitation for molecular MRD.

### Marking criteria

- **R1C1:** Confirm **AML**. DNMT3A R882H and truncating TET2 support clonality but do not independently define another AML entity or AML with myelodysplasia-related genetic abnormalities.
- **R2C1:** Apply ELN 2022 and assign the applicable **intermediate-risk** category from the supplied normal cytogenetics and absence of an ELN favourable- or adverse-defining molecular finding.

## Case 1B — NPM1-mutated AML with FLT3-TKD

### Clinical information

**NGS:** `NPM1` type A, NM_002520.7:c.860_863dup, p.(Trp288CysfsTer12), VAF 41%; `FLT3` NM_004119.3:c.2503G>T, p.(Asp835Tyr), VAF 24%.

**Cytogenetics:** Normal.

### NEL task

Assign the NPM1-defined AML entity, apply the appropriate ELN category, report the FLT3-TKD treatment implication, and identify the preferred molecular MRD target.

### Marking criteria

- **R1C1:** State **AML with mutated NPM1**. FLT3-TKD does not displace the NPM1-defined entity.
- **R2C1:** Assign **ELN 2022 favourable risk** in the supplied setting without FLT3-ITD or an adverse-risk defining finding.
- **R3C1:** State that FLT3 D835Y is a therapeutically actionable FLT3-TKD alteration in the appropriate AML treatment setting, with treatment phase and approval/access qualified where relevant.
- **R4C1:** Identify the exact NPM1 mutation (type A, or the exact HGVS) as the preferred dedicated high-sensitivity molecular MRD target.

## Case 1C — PML::RARA-positive acute promyelocytic leukaemia

### Clinical information

**FISH:** `PML::RARA` rearrangement positive.

**NGS:** `FLT3` internal tandem duplication, NM_004119.3:c.1773_1793dup, VAF 32%; `KRAS` NM_004985.5:c.35G>A, p.(Gly12Asp), VAF 4%.

### NEL task

Integrate the defining FISH result with NGS, respect diagnostic precedence, and distinguish the roles of the secondary NGS findings.

### Marking criteria

- **R1C1:** Refine the diagnosis to **acute promyelocytic leukaemia with PML::RARA**. The defining PML::RARA rearrangement takes diagnostic precedence over FLT3-ITD and low-level KRAS.
- **R3C1:** Recognise that the disease-defining PML::RARA finding has an immediate disease-specific treatment implication even though it was detected outside the NGS assay.
- **R4C1:** Identify `PML::RARA` as the appropriate leukaemia-specific molecular follow-up target; FLT3-ITD or KRAS must not replace it as the principal MRD marker.

## Case 1D — AML with myelodysplasia-related gene mutations

### Clinical information

**NGS:** `SRSF2` NM_003016.5:c.284C>A, p.(Pro95His), VAF 41%; `ASXL1` NM_015338.6:c.1934dup, p.(Gly646TrpfsTer12), VAF 34%; `TET2` NM_001127208.3:c.1132_1133del, p.(Gly378CysfsTer11), VAF 45%.

**Cytogenetics:** Normal.

### NEL task

Recognise the myelodysplasia-related molecular classification, apply ELN 2022, and avoid promoting the detected mutations to stand-alone MRD markers.

### Marking criteria

- **R1C1:** State **AML, myelodysplasia-related** on the basis of qualifying myelodysplasia-related gene mutation(s), including SRSF2 and ASXL1.
- **R2C1:** Assign **ELN 2022 adverse risk** because of the qualifying myelodysplasia-related gene mutation(s).

## Case 1E — CALR type 1 in an AML presentation

### Clinical information

**NGS:** `CALR` type 1, NM_004343.4:c.1099_1150del, p.(Leu367fs), VAF 44%.

**Cytogenetics:** Normal.

No previous diagnosis of an MPN is documented.

### NEL task

Preserve the supplied AML diagnosis while recognising the significance and limitation of an MPN-associated CALR driver in this setting.

### Marking criteria

- **R1C1:** Preserve the supplied **AML** diagnosis. CALR type 1 strongly raises the possibility of an antecedent or occult MPN but does not by itself establish MPN blast-phase disease without the required clinicopathological history or morphology.
- **R2C1:** Assign the applicable **ELN 2022 intermediate-risk** category from the supplied findings; CALR is not itself an ELN favourable- or adverse-risk defining lesion.
- **R4C1:** Do not treat CALR as a validated stand-alone AML MRD marker.

---

# Case 2 — MDS with 12% blasts

## Shared stem

Cytopenias and marrow dysplasia are present. Marrow blasts are 12%. Provisional diagnosis: **myelodysplastic neoplasm with increased blasts-2 (MDS-IB2)**.

## Case 2A — TET2, CBL and EZH2 with normal cytogenetics

### Clinical information

**NGS:** `TET2` NM_001127208.3:c.1132_1133del, p.(Gly378CysfsTer11), VAF 43%; `CBL` NM_005188.4:c.1111T>C, p.(Tyr371His), VAF 31%; `EZH2` NM_004456.5:c.862C>T, p.(Arg288Ter), VAF 28%.

**Cytogenetics:** Normal.

### NEL task

Apply the blast-defined WHO-5 diagnosis and recognise the materially different ICC molecular entity without constructing an incomplete prognostic score.

### Marking criteria

- **R1C1:** State **WHO-5 MDS with increased blasts-2 (MDS-IB2)**.
- **R1C2:** State the materially different ICC classification of **MDS/AML with myelodysplasia-related gene mutation(s)** because EZH2 is a qualifying myelodysplasia-related gene.
- **R2C1:** State CBL and EZH2 are among the main-effect genes in the IPSS-M conferring adverse prognosis.

## Case 2B — TP53 mutation with 17p deletion

### Clinical information

**NGS:** `TP53` NM_000546.6:c.743G>A, p.(Arg248Gln), VAF 48%.

**Cytogenetics/FISH:** del(17p) involving `TP53`.

### NEL task

Integrate the mutation and cytogenetic second hit and apply the materially different WHO-5 and ICC classifications.

### Marking criteria

- **R1C1:** State **WHO-5 MDS with biallelic TP53 inactivation**
- **R1C2:** State the materially different ICC entity **MDS/AML with mutated TP53**.
- **R2C1:** Report TP53 multi-hit status as the dominant adverse molecular feature as per IPSS-M.

## Case 2C — Single TP53 mutation with cytogenetics pending

### Clinical information

**NGS:** `TP53` NM_000546.6:c.818G>A, p.(Arg273His), VAF 36%.

**Cytogenetics:** Pending.

### NEL task

Apply the classification that can be established from the available result while keeping TP53 allelic state unresolved where additional testing is required.

### Marking criteria

- **R1C1:** State **WHO-5 MDS-IB2**; biallelic TP53 inactivation is not established from the single mutation alone while cytogenetic/copy-number assessment remains pending.
- **R1C2:** State the materially different ICC classification **MDS/AML with mutated TP53**.
- **R2C1:** State that TP53 single-hit status is not adversely prognosis as per IPSS-M in the absence of biallelic TP53.

## Case 2D — Negative NGS with cytogenetics pending

### Clinical information

**NGS:** No pathogenic or likely pathogenic variants detected.

**Cytogenetics:** Pending.

### NEL task

Preserve the morphologically established disease despite a negative SNV/indel panel and recognise the limits imposed by pending cytogenetics.

### Marking criteria

- **R1C1:** State **WHO-5 MDS-IB2**. A negative NGS panel does not negate the supplied morphologically established MDS.
- **R1C2:** State that under ICC the case lies in the **MDS/AML blast range**, but final genetic subclassification cannot be completed while cytogenetic information is pending.
- **R2C1:** Do not assign a complete molecular/cytogenetic prognostic category while required cytogenetic information remains unavailable.

## Case 2E — SF3B1 K666N with increased blasts

### Clinical information

**NGS:** `SF3B1` NM_012433.4:c.1998G>T, p.(Lys666Asn), VAF 37%.

**Cytogenetics:** Normal.

### NEL task

Apply the blast requirement rather than allowing an SF3B1 mutation to force a low-blast entity, and state the material ICC divergence.

### Marking criteria

- **R1C1:** State **WHO-5 MDS-IB2**, not MDS with low blasts and SF3B1 mutation, because the supplied 12% marrow blasts preclude the low-blast SF3B1-defined entity.
- **R1C2:** State the materially different ICC entity **MDS/AML with myelodysplasia-related gene mutation(s)**, with SF3B1 providing the qualifying molecular feature.
- **R2C1:** Recognise SF3B1 is favourable prognosis in IPSS-M

---

# Case 3 — MPN/CMML differential in a leukoerythroblastic presentation

## Shared stem

Leukoerythroblastic blood film. Hb 180 g/L, WCC 15 × 10^9/L and platelets 450 × 10^9/L.

## Case 3A — JAK2 V617F

### Clinical information

Provisional diagnosis: **primary myelofibrosis (PMF)**.

**NGS:** `JAK2` NM_004972.4:c.1849G>T, p.(Val617Phe), VAF 55%.

### NEL task

Use JAK2 as molecular support for the supplied PMF diagnosis without allowing genotype or blood counts alone to replace the supplied morphology.

### Marking criteria

- **R1C1:** Confirm molecular support for **PMF**. JAK2 V617F supports an MPN clone but is not specific for PMF and does not independently distinguish PMF from another JAK2-mutated MPN.

## Case 3B — CALR type 2

### Clinical information

Provisional diagnosis: **primary myelofibrosis (PMF)**.

**NGS:** `CALR` type 2, NM_004343.4:c.1154_1155insTTGTC, p.(Lys385fs), VAF 42%.

### NEL task

Confirm molecular support for PMF and distinguish CALR type 2 from the favourable type 1/type 1-like category used in PMF prognostic models.

### Marking criteria

- **R1C1:** Confirm molecular support for **CALR-mutated PMF** in the supplied clinicomorphological context.
- **R2C1:** State that CALR type 2 is **not equivalent to the favourable CALR type 1/type 1-like category** used by MIPSS70+v2.

## Case 3C — IDH2 without a canonical MPN driver

### Clinical information

Provisional diagnosis: **primary myelofibrosis (PMF)**.

**NGS:** `IDH2` NM_002168.4:c.419G>A, p.(Arg140Gln), VAF 33%. No pathogenic `JAK2`, `CALR` or `MPL` variant is detected.

### NEL task

Preserve the clinicomorphological PMF diagnosis despite absence of a canonical driver and report the disease-specific prognostic effect of IDH2.

### Marking criteria

- **R1C1:** Preserve the supplied **PMF** diagnosis. IDH2 supports clonality but is not a canonical PMF driver, and absence of JAK2/CALR/MPL does not by itself exclude PMF.
- **R2C1:** Report IDH2 as a **high-molecular-risk/adverse molecular finding in PMF** as per MIPSS70+v2.

## Case 3D — Persistent monocytosis with RAS-pathway mutations

### Clinical information

Provisional diagnosis: **MDS with monocytosis**.

Monocytes are 2.25 × 10^9/L and 15% of the WCC. Monocytosis is persistent and otherwise unexplained. Reactive causes have been excluded.

**NGS:** `PTPN11` NM_002834.5:c.226G>A, p.(Glu76Lys), VAF 30%; `NF1` NM_001042492.3:c.2041C>T, p.(Arg681Ter), VAF 27%; `CBL` NM_005188.4:c.1111T>C, p.(Tyr371His), VAF 35%.

### NEL task

Use the supplied sustained monocytosis and molecular findings to reconsider the provisional MDS diagnosis without making the genotype independently diagnostic.

### Marking criteria

- **R1C1:** Refine the diagnosis to **CMML** given the supplied qualifying persistent absolute and relative monocytosis and exclusion of reactive causes.
- **R1C2:** State that the PTPN11/NF1/CBL RAS-pathway genotype supports clonal/proliferative biology but does not independently establish CMML without the required clinical and morphological criteria.
- **R1C3:** Recognise the **myeloproliferative CMML phenotype** from WCC >13 × 10^9/L. Do not assign a blast-based CMML subgroup when blast information is not supplied.

---

# Case 4 — Variant-specific diagnostic support

## Shared stem

No shared clinical stem. Clinical information is variant-specific.

## Case 4A — KIT D816V in systemic mastocytosis

### Clinical information

Recurrent flushing and anaphylactoid episodes. Serum tryptase is persistently elevated. Marrow shows multifocal dense mast-cell aggregates with spindle-cell morphology and aberrant CD25 expression.

Provisional diagnosis: **systemic mastocytosis**.

**NGS:** `KIT` NM_000222.3:c.2447A>T, p.(Asp816Val), VAF 4%.

### NEL task

Integrate a low-VAF KIT D816V result with an already supportive clinicomorphological picture.

### Marking criteria

- **R1C1:** Confirm that KIT D816V provides strong molecular support for the supplied **systemic mastocytosis** diagnosis. The low VAF does not invalidate an otherwise established diagnosis.

## Case 4B — CSF3R T618I in chronic neutrophilic leukaemia

### Clinical information

Persistent WCC 34 × 10^9/L with 88% mature neutrophils, circulating myeloid precursors <2%, no significant dysgranulopoiesis, and monocytes and basophils below exclusion thresholds. Reactive neutrophilia and relevant defining rearrangements have been excluded.

Provisional diagnosis: **chronic neutrophilic leukaemia (CNL)**.

**NGS:** `CSF3R` NM_000760.4:c.1853C>T, p.(Thr618Ile), VAF 44%.

### NEL task

Confirm molecular support for the supplied CNL diagnosis without allowing genotype alone to replace the required clinicopathological context.

### Marking criteria

- **R1C1:** Confirm **CNL**. CSF3R T618I provides strong diagnostic molecular support in the supplied clinicomorphological context.

## Case 4C — BRAF V600E in suspected hairy cell leukaemia

### Clinical information

Splenomegaly and circulating hairy cells are present. Peripheral-blood flow cytometry demonstrates a clonal mature B-cell population with an immunophenotype typical of classic hairy cell leukaemia. Trephine biopsy is pending.

Provisional diagnosis: **hairy cell leukaemia**.

**NGS:** `BRAF` NM_004333.6:c.1799T>A, p.(Val600Glu), VAF 22%.

### NEL task

Use the BRAF result to support the supplied diagnosis while respecting the pending pathological assessment.

### Marking criteria

- **R1C1:** State that **BRAF V600E strongly supports classic hairy cell leukaemia** in the supplied clinical and immunophenotypic context.
- **R1C2:** Keep the interpretation integrated with the supplied blood/flow findings rather than treating BRAF V600E alone as independently diagnostic; the pending trephine may further establish the pathological diagnosis.

## Case 4D — MYD88 L265P in an IgM-secreting lymphoid neoplasm

### Clinical information

IgM paraprotein 20 g/L. Marrow/flow assessment demonstrates a 20% monoclonal small B-cell/lymphoplasmacytic population.

Provisional diagnosis: **lymphoplasmacytic lymphoma / Waldenström macroglobulinaemia**.

**NGS:** `MYD88` NM_002468.4:c.794T>C, p.(Leu265Pro), VAF 32%.

### NEL task

Use the MYD88 hotspot as molecular support for the supplied lymphoplasmacytic diagnosis without treating it as disease-specific in isolation.

### Marking criteria

- **R1C1:** State that **MYD88 L265P strongly supports lymphoplasmacytic lymphoma/Waldenström macroglobulinaemia** in the supplied IgM-secreting lymphoplasmacytic context.
- **R1C2:** State that MYD88 L265P is supportive rather than independently specific; diagnosis remains an integrated clinicopathological assessment.

---

# Case 5 — Possible germline predisposition in provisional CCUS

## Shared stem

Persistent pancytopenia. Marrow shows mild/borderline trilineage dysplasia that is insufficient for a morphological diagnosis of MDS. Blasts are not increased.

Provisional diagnosis: **CCUS**.

The NGS assay is tumour-only. No constitutional specimen has been tested. No family-history information is supplied.

## Case 5A — Possible germline DDX41

### Clinical information

**NGS:** `DDX41` NM_016222.4:c.415_418dup, p.(Asp140GlyfsTer2), VAF 46%.

**Cytogenetics:** Normal.

### NEL task

Recognise a characteristic possible germline DDX41 loss-of-function variant, preserve the distinction between CCUS and MDS, and state the implications of constitutional confirmation.

### Marking criteria

- **R1C1:** Do not upgrade the borderline marrow findings to MDS. If the DDX41 variant proves constitutional, that variant itself does not establish an acquired clone, so CCUS would require another acquired clonal marker.
- **R5C1:** Flag **possible germline DDX41 predisposition**. Do not call the tumour-only finding definitively germline.

## Case 5B — Possible germline RUNX1

### Clinical information

**NGS:** `RUNX1` NM_001754.5:c.496C>T, p.(Arg166Ter), VAF 34%.

**Cytogenetics:** Normal.

### NEL task

Recognise a pathogenic RUNX1 loss-of-function variant as a possible constitutional predisposition despite a VAF below the classic near-50% range.

### Marking criteria

- **R1C1:** Do not diagnose MDS from the RUNX1 mutation in a marrow explicitly insufficient for MDS. If constitutional, the RUNX1 variant does not itself establish an acquired clone, so CCUS would require another acquired clonal marker.
- **R5C1:** Flag **possible germline RUNX1 predisposition** despite the 34% tumour VAF. VAF alone must not determine somatic versus germline origin.

## Case 5C — Possible germline CEBPA

### Clinical information

**NGS:** `CEBPA` NM_004364.5:c.68dup, p.(His24AlafsTer84), VAF 63%.

**Cytogenetics:** Normal.

### NEL task

Recognise a germline-compatible N-terminal CEBPA truncating variant without treating either the high VAF or the gene name as evidence of AML.

### Marking criteria

- **R1C1:** Preserve the supplied non-MDS clinicomorphological context and do not diagnose CEBPA-mutated AML. If constitutional, the isolated CEBPA variant does not itself establish an acquired clone.
- **R5C1:** Flag **possible germline CEBPA predisposition**. A 63% tumour VAF must not be interpreted as proof of constitutional origin.

## Case 5D — ANKRD26 5′ UTR hotspot

### Clinical information

**NGS:** `ANKRD26` NM_014915.3:c.-128G>A, VAF 51%.

**Cytogenetics:** Normal.

### NEL task

Recognise the characteristic regulatory-region architecture of ANKRD26-related hereditary predisposition and distinguish possible constitutional status from evidence of an acquired myeloid clone.

### Marking criteria

- **R1C1:** Do not upgrade the borderline marrow findings to MDS. If the ANKRD26 variant proves constitutional, it does not itself establish an acquired clone, so CCUS would require another acquired clonal marker.
- **R5C1:** Flag **possible germline ANKRD26 predisposition**, recognising the characteristic 5′ UTR variant architecture. Do not infer germline status from the 51% VAF alone.

