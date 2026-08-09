# NEL-focused case set

## Purpose

These cases test whether the NGS Evidence Layer (NEL) correctly explains how an NGS result **confirms, changes, excludes or qualifies an explicitly supplied clinicomorphological diagnosis**, and how the result affects prognosis, actionability, MRD interpretation or possible germline predisposition.

NEL is not asked to derive a morphological diagnosis from a clinical vignette or to supply missing diagnostic criteria.

## Design conventions

- Each case supplies an explicit provisional clinicomorphological diagnosis.
- Only clinical, morphological and laboratory facts needed to interpret the NGS result are retained.
- WHO-5 is primary. ICC is required only when it produces a materially different entity.
- Complete prognostic scores are not required unless every input is supplied. Otherwise, report only the molecular contribution.
- Negative findings are retained only when they change diagnosis, allelic state, assay interpretation or management.
- Bulk VAF does not establish mutation order, phase, shared clonality or germline status.
- Negative instructions in NEL tasks are guard conditions: they are assessed only if the report makes the prohibited claim and do not require a negative sentence.

### Germline-screening convention

Personal or family history is **not required** before possible germline origin is considered.

A pathogenic or likely pathogenic variant in a recognised haematological-predisposition gene should trigger germline review when detected on tumour-only testing at **VAF >30%**, with **40–60%** being the typical near-heterozygous range. The decision to flag possible germline origin must also consider the exact variant, gene-specific somatic patterns, copy-number or loss-of-heterozygosity findings, and characteristic molecular architecture. Germline status must never be assigned from tumour-only testing and requires confirmation in a validated non-haematopoietic specimen.

A low-VAF recurrent somatic second event, characteristic phenotype or incomplete panel coverage may also justify constitutional testing even when no near-heterozygous variant is detected.

## Removed case variants

- **Case 5C** — removed because the diagnosis and therapeutic implication are determined by a cytogenetic/FISH-detected `ETV6::PDGFRB` rearrangement rather than the NGS assay. This is better tested as an assay-integration case outside the core NEL variant set.

---

# Case 1 — MDS with ring sideroblasts

## Shared stem

74F with anaemia.

## Case 1A — SF3B1-confirmed entity

### Clinical information

Hb 92 g/L. Marrow shows a myelodysplastic neoplasm with low blasts and ring sideroblasts comprising 22% of erythroid precursors.

**NGS:** `SF3B1` p.(Lys700Glu), VAF 38%.  
**Cytogenetics:** Normal.

### NEL task

Confirm that the molecular result refines the supplied diagnosis to MDS with low blasts and an SF3B1 mutation, and report the favourable isolated-SF3B1 molecular contribution.

### Marking criteria

- **R1C1:** State **MDS with low blasts and SF3B1 mutation (MDS-SF3B1)**. The qualifying SF3B1 variant confirms the entity in the supplied low-blast MDS context.
- **R2C1:** State that isolated SF3B1 is a favourable molecular contribution.

## Case 1B — SF3B1-wild-type ring-sideroblast MDS

### Clinical information

Hb 92 g/L. Marrow shows a myelodysplastic neoplasm with low blasts and ring sideroblasts comprising 22% of erythroid precursors.

**Additional finding:** SF3B1 pathogenic variants are not detected.  
**NGS:** `SRSF2` p.(Pro95Arg), VAF 31%.  
**Cytogenetics:** Normal.

### NEL task

Avoid substituting SRSF2 for SF3B1, preserve the appropriate WHO-5 ring-sideroblast entity, state the material ICC divergence, and report the adverse SRSF2 molecular contribution.

### Marking criteria

- **R1C1:** State **WHO-5 MDS with low blasts and ring sideroblasts**, not MDS-SF3B1. Under ICC, classify as **MDS, NOS**.
- **R1C2:** Explain that absence of SF3B1 prevents use of the SF3B1-defined entity despite 22% ring sideroblasts; SRSF2 is not a substitute.
- **R2C1:** Report SRSF2 as an adverse molecular contribution.

## Case 1C — WHO-5/ICC divergence from RUNX1

### Clinical information

Hb 92 g/L. Marrow shows a myelodysplastic neoplasm with low blasts and ring sideroblasts comprising 22% of erythroid precursors.

**NGS:** `SF3B1` p.(Lys700Glu), VAF 36%; `RUNX1` p.(Arg201Gln), VAF 20%.  
**Cytogenetics:** Normal.

### NEL task

Apply WHO-5 as primary, identify the material ICC exclusion created by RUNX1, separate classification from prognosis, and avoid inferring clonal order from VAF.

### Marking criteria

- **R1C1:** State **WHO-5 MDS-SF3B1**. State the materially different ICC classification of **MDS, NOS**, because RUNX1 excludes the ICC SF3B1 entity.
- **R2C1:** Report RUNX1 as an adverse molecular contribution.

## Case 1D — CCUS, not MDS

### Clinical information

The anaemia is persistent and otherwise unexplained. Marrow is non-diagnostic for a myeloid neoplasm: ring sideroblasts 6%, low blasts and no diagnostic dysplasia.

**NGS:** `SF3B1` p.(Lys700Glu), VAF 4%.  
**Cytogenetics:** Normal.

### NEL task

Classify a small clone in an explicitly unexplained cytopenia as CCUS and avoid diagnosing MDS from the mutation alone.

### Marking criteria

- **R1C1:** State **CCUS**, because cytopenia is persistent and otherwise unexplained and the marrow does not establish a myeloid neoplasm.
- **R1C2:** A 4% SF3B1 clone supports clonal haematopoiesis but does not establish MDS.

---

# Case 2 — Small clone versus established MDS

## Shared stem

59F.

## Case 2A — CHIP with an adequate external cause

### Clinical information

Iron-deficiency anaemia is present. Hb 89 g/L, MCV 76 fL, ferritin 7 micrograms/L and transferrin saturation 4%. WCC and platelets are normal. The anaemia is clinically attributed to iron deficiency. No morphological myeloid neoplasm is present.

**NGS:** `SRSF2` p.(Pro95His), VAF 4%.

### NEL task

Recognise CHIP when a small clone is present but the supplied cytopenia has an adequate external explanation.

### Marking criteria

- **R1C1:** State **CHIP**, not CCUS or MDS, while iron deficiency adequately explains the anaemia.
- **R1C2:** A 4% SRSF2 clone is small and must not independently establish a myeloid neoplasm.

## Case 2B — Molecular qualification of supplied MDS

### Clinical information

Cytopenias are present. Marrow shows multilineage dysplasia, 3% blasts and no fibrosis. Provisional diagnosis: **MDS with low blasts and multilineage dysplasia**. The absolute and relative monocyte counts are below CMML thresholds.

**NGS:** `SRSF2` p.(Pro95His), VAF 42%; `TET2` p.(Arg1261Cys), VAF 46%; `ASXL1` p.(Gly646TrpfsTer12), VAF 20%.  
**Cytogenetics:** Normal.

### NEL task

Confirm the supplied MDS diagnosis, recognise that a CMML-like genotype cannot override absent monocytosis, and report the adverse molecular contribution.

### Marking criteria

- **R1C1:** Confirm **MDS with low blasts**. Do not diagnose CMML from the genotype when qualifying monocytosis is explicitly absent.
- **R2C1:** Report SRSF2 and ASXL1 as adverse molecular contributions.

## Case 2C — Blast-range divergence and possible germline RUNX1

### Clinical information

Thrombocytopenia and easy bruising have been documented since early adulthood. Marrow shows dysplasia and 12% blasts. Provisional diagnosis: **MDS with increased blasts-2**.

**NGS:** `SRSF2` p.(Pro95His), VAF 40%; truncating `RUNX1` p.(Arg166Ter), VAF 48%; `ASXL1` p.(Gly646TrpfsTer12), VAF 25%.  
**Cytogenetics:** Normal.

### NEL task

State the WHO-5/ICC blast-range divergence, report adverse molecular findings, and flag possible germline RUNX1.

### Marking criteria

- **R1C1:** State **WHO-5 MDS-IB2** and the materially different ICC entity **MDS/AML with myelodysplasia-related gene mutations**.
- **R2C1:** Report SRSF2, RUNX1 if somatic, and ASXL1 as adverse molecular contributions.
- **R5C1:** Flag **possible germline RUNX1**. The truncating variant at 48% VAF is in the near-heterozygous range; the longstanding platelet phenotype strengthens suspicion. Recommend genetic counselling and confirmation in a validated non-haematopoietic specimen.

---

# Case 3 — TP53 allelic state

## Shared stem

68M with pancytopenia. Marrow shows a myelodysplastic neoplasm with trilineage dysplasia. Blast percentage and TP53 findings vary by case.

## Case 3A — Single monoallelic TP53 mutation

### Clinical information

Marrow blasts 4%. Provisional diagnosis: **MDS with low blasts**.

**NGS:** `TP53` p.(Arg175His), VAF 12%.  
**Cytogenetics/FISH:** Normal karyotype; no 17p deletion or copy-neutral LOH detected.

### NEL task

Avoid overcalling biallelic or multi-hit TP53 disease and avoid assigning its major adverse prognostic weight.

### Marking criteria

- **R1C1:** State **MDS with low blasts**, not MDS with biallelic TP53 inactivation.
- **R1C2:** A single 12% TP53 mutation without a qualifying second hit does not establish biallelic disease.
- **R2C1:** Interpret the TP53 finding as monoallelic rather than TP53-multihit and do not assign the multihit adverse weight.

## Case 3B — Two qualifying TP53 mutations

### Clinical information

Marrow blasts 6%. Provisional diagnosis: **MDS with increased blasts-1**.

**NGS:** `TP53` p.(Arg248Gln), VAF 22%; `TP53` p.(Tyr220Cys), VAF 18%.  
**Cytogenetics:** Normal.

### NEL task

Recognise two qualifying TP53 mutations as multi-hit/biallelic disease and report the major adverse molecular contribution.

### Marking criteria

- **R1C1:** State **MDS with biallelic TP53 inactivation** under the supplied classification criteria.
- **R2C1:** State that TP53-multihit is the dominant adverse molecular feature.

## Case 3C — Mutation plus 17p deletion

### Clinical information

Marrow blasts 14%. Provisional diagnosis: **MDS with increased blasts-2**.

**NGS:** `TP53` p.(Arg273His), VAF 46%.  
**Cytogenetics/FISH:** Complex karyotype with del(17p); TP53-deletion FISH positive.

### NEL task

Integrate NGS with the supplied cytogenetic second hit, apply WHO-5/ICC divergence, and avoid mistaking near-heterozygous VAF for proof of germline origin.

### Marking criteria

- **R1C1:** Mutation plus del(17p) supports **multi-hit/biallelic TP53** disease.
- **R1C2:** State **WHO-5 MDS with biallelic TP53 inactivation** and the materially different ICC entity **MDS/AML with mutated TP53**.
- **R2C1:** Report the major adverse TP53-multihit molecular contribution.

---

# Case 4 — NPM1-mutated AML

## Shared stem

63M. Marrow shows acute myeloid leukaemia with 68% blasts. Cytogenetics are normal.

## Case 4A — NPM1 with DNMT3A

### Clinical information

**NGS:** `NPM1` type A, VAF 40%; `DNMT3A` p.(Arg882His), VAF 44%.

### NEL task

Assign the NPM1-defined AML entity, apply the appropriate ELN category, identify NPM1 as the MRD marker, and avoid using DNMT3A for MRD status.

### Marking criteria

- **R1C1:** State **AML with mutated NPM1**.
- **R2C1:** Apply ELN 2022 and assign the applicable favourable category; DNMT3A does not downgrade it.
- **R3C1:** State the NPM1/menin-pathway treatment implication in the eligible relapsed/refractory setting, with approval and jurisdiction qualified.
- **R4C1:** Identify the exact NPM1 mutation as the preferred high-sensitivity molecular MRD target.

## Case 4B — NPM1 with FLT3-ITD

### Clinical information

**NGS:** `NPM1` type A, VAF 40%; `FLT3-ITD`, allelic ratio approximately 0.3.

### NEL task

Keep the NPM1 entity, apply the current FLT3-ITD risk rule without using allelic ratio, report FLT3 actionability, and use FLT3-ITD only as a complementary MRD marker when NPM1 is available.

### Marking criteria

- **R1C1:** State **AML with mutated NPM1**; FLT3-ITD changes prognosis and therapy, not entity assignment.
- **R2C1:** Apply ELN 2022 and assign the applicable intermediate category.
- **R3C1:** State the FLT3-directed treatment implications in the relevant frontline and relapsed/refractory settings.
- **R4C1:** Use NPM1 as the primary molecular MRD target; FLT3-ITD is complementary within a validated high-sensitivity strategy.

## Case 4C — NPM1 with myelodysplasia-related co-mutations

### Clinical information

**NGS:** `NPM1` type A, VAF 40%; `SRSF2` p.(Pro95His), VAF 38%; `STAG2` p.(Arg1033Ter), VAF 42%.

### NEL task

Respect NPM1 diagnostic precedence, keep entity assignment separate from co-mutation biology, preserve the applicable ELN category, and avoid promoting SRSF2 or STAG2 to stand-alone MRD markers.

### Marking criteria

- **R1C1:** State **AML with mutated NPM1**; the NPM1 entity takes precedence over the MR-gene qualifier.
- **R2C1:** Preserve the applicable ELN 2022 favourable category because the selected framework does not use these co-mutations to override it in this setting.
- **R4C1:** Use NPM1 as the preferred MRD marker.

---

# Case 5 — CMML versus another MDS/MPN

## Shared stem

72M with a supplied myelodysplastic/myeloproliferative neoplasm, WCC 24 × 10^9/L, 4% marrow blasts and BCR::ABL1 negative status.

## Case 5A — Confirmed proliferative CMML

### Clinical information

Monocytes are 3.6 × 10^9/L and 15% of WCC. Qualifying monocytosis is sustained and reactive causes are excluded. Provisional diagnosis: **CMML-1, myeloproliferative type**.

**NGS:** `TET2` splice variant, VAF 44%; `SRSF2` p.(Pro95His), VAF 40%; `ASXL1` p.(Gly646TrpfsTer12), VAF 22%; `NRAS` p.(Gly12Asp), VAF 18%.  
**Cytogenetics:** Normal.

### NEL task

Confirm the supplied CMML diagnosis, explain the molecular support and proliferative biology, and report the disease-appropriate adverse molecular contributions without constructing an incomplete score.

### Marking criteria

- **R1C1:** Confirm **MP-CMML-1** because the mandatory monocytosis and exclusion facts are supplied; the genotype is supportive rather than independently diagnostic.
- **R2C1:** Report ASXL1 and NRAS as adverse molecular contributions in the CMML framework.

## Case 5B — CMML-like genotype without qualifying monocytosis

### Clinical information

Monocytes are 0.7 × 10^9/L and 2.9% of WCC. Marrow and clinical review establish **MDS/MPN, NOS** after exclusion of other defined entities.

**NGS:** `TET2` splice variant, VAF 42%; `SRSF2` p.(Pro95His), VAF 38%; `ASXL1` p.(Gly646TrpfsTer12), VAF 20%.  
**Cytogenetics:** Normal.

### NEL task

Avoid diagnosing CMML from a characteristic genotype when a mandatory relative-monocyte criterion is not met, and avoid applying an MDS prognostic model to an MDS/MPN.

### Marking criteria

- **R1C1:** Confirm **MDS/MPN, NOS**. Do not diagnose CMML because the relative monocytosis threshold is not met.
- **R2C1:** Give only cautious disease-specific molecular commentary.

---

# Case 6 — Thrombocytosis and MPN classification

## Shared stem

48F with persistent thrombocytosis, platelet count 780 × 10^9/L and BCR::ABL1 negative status. Marrow diagnosis and driver findings vary by case.

## Case 6A — CALR-mutated ET

### Clinical information

Marrow morphology is diagnostic of **essential thrombocythaemia**, with MF-0 and no prefibrotic-PMF morphology. JAK2 and MPL pathogenic variants are not detected.

**NGS:** `CALR` type 2, VAF 42%.

### NEL task

Confirm molecular clonality in an explicitly diagnosed ET case and apply the supplied ET thrombosis variables without re-diagnosing marrow morphology.

### Marking criteria

- **R1C1:** Confirm **CALR-mutated ET** in the supplied ET morphology.
- **R2C1:** Apply revised IPSET-thrombosis using age under 60, no previous thrombosis and JAK2-unmutated status; assign the applicable very-low-risk group.

## Case 6B — Confirmed prefibrotic PMF

### Clinical information

Marrow shows dense atypical megakaryocyte clusters, granulocytic proliferation and MF-1. LDH is elevated, providing a qualifying minor clinical criterion. Provisional diagnosis: **prefibrotic/early primary myelofibrosis**.

**NGS:** `CALR` type 1, VAF 44%; `ASXL1` frameshift, VAF 30%.  
**Cytogenetics:** Normal.

### NEL task

Confirm molecular support for the supplied prefibrotic-PMF diagnosis and report the ASXL1 high-molecular-risk contribution without calculating an incomplete PMF score.

### Marking criteria

- **R1C1:** Confirm **prefibrotic/early PMF** in the supplied diagnostic context.
- **R2C1:** Report ASXL1 as a high-molecular-risk finding.

## Case 6C — Possible hereditary MPL thrombocytosis

### Clinical information

Thrombocytosis has been documented since adolescence. Marrow has an ET-like appearance. JAK2 and CALR pathogenic variants are not detected.

**NGS:** `MPL` p.(Ser505Asn), VAF 49%.  
**Cytogenetics:** Normal.

### NEL task

Recognise possible germline MPL-related hereditary thrombocytosis, avoid automatically diagnosing acquired ET, and defer ET-specific risk scoring until constitutional status is resolved.

### Marking criteria

- **R1C1:** State that acquired ET cannot be finalised until possible hereditary `MPL` p.(Ser505Asn) thrombocytosis is excluded.
- **R5C1:** Flag **possible germline MPL**. The recognised predisposition variant at 49% VAF warrants constitutional review; thrombocytosis from adolescence strengthens suspicion. Recommend genetic counselling and validated non-haematopoietic testing.

---

# Case 7 — Systemic mastocytosis

## Shared stem

55F with a supplied diagnosis of systemic mastocytosis based on dense mast-cell aggregates and aberrant mast-cell immunophenotype.

## Case 7A — Low-VAF KIT D816V in indolent SM

### Clinical information

No B- or C-findings. Provisional diagnosis: **indolent systemic mastocytosis**.

**NGS:** `KIT` p.(Asp816Val), VAF 2%. The remainder of the myeloid panel is negative.

### NEL task

Avoid dismissing an established diagnosis because KIT D816V has a low allele burden and report relevant KIT-directed actionability.

### Marking criteria

- **R1C1:** Confirm the supplied **indolent systemic mastocytosis** diagnosis. A 2% KIT D816V VAF is compatible with low mast-cell representation and does not argue against the diagnosis.
- **R3C1:** State the KIT-directed treatment implication for symptomatic indolent disease where approved and available.

## Case 7B — SM with independently confirmed CMML

### Clinical information

Systemic mastocytosis and CMML independently meet their diagnostic criteria. Qualifying monocytosis is sustained and reactive causes are excluded. Provisional diagnosis: **systemic mastocytosis with associated CMML**.

**NGS:** `KIT` p.(Asp816Val), VAF 32%; `SRSF2` p.(Pro95His), VAF 30%; `ASXL1` p.(Gly646TrpfsTer12), VAF 24%.

### NEL task

Confirm the supplied dual entity, keep molecular support separate from the independently established CMML diagnosis, and report advanced-SM adverse molecular features and KIT actionability.

### Marking criteria

- **R1C1:** State **SM with an associated haematological neoplasm, CMML**. The genotype supports but does not independently establish CMML.
- **R2C1:** Report SRSF2 and ASXL1 as adverse molecular findings in advanced SM.
- **R3C1:** State the KIT D816V-directed treatment implication and keep management of the associated CMML separate.

## Case 7C — Non-D816V KIT and possible germline origin

### Clinical information

Cutaneous mastocytosis lesions have been present since childhood. KIT D816V is not detected.

**NGS:** `KIT` p.(Lys509Ile), VAF 49%.

### NEL task

Interpret the exact non-D816V KIT variant, avoid applying D816V-specific treatment logic, and flag possible germline KIT even without making personal history a prerequisite.

### Marking criteria

- **R1C1:** State systemic mastocytosis with an atypical non-D816V KIT mutation.
- **R3C1:** Any imatinib-sensitivity statement must be cautious and variant-specific.
- **R5C1:** Flag **possible germline KIT**. The recognised activating variant at 49% VAF is sufficient to trigger constitutional review; the childhood phenotype strengthens suspicion. Recommend genetic counselling and validated non-haematopoietic testing.

---

# Case 8 — Germline-predisposition architectures

## Shared stem

66M with a supplied myeloid-neoplasm diagnosis. Molecular findings vary by case.

## Case 8A — Near-heterozygous DDX41 loss-of-function plus low-VAF second event

### Clinical information

Marrow shows hypocellular MDS with low blasts and multilineage dysplasia.

**NGS:** `DDX41` p.(Asp140GlyfsTer2), VAF 48%; `DDX41` p.(Arg525His), VAF 9%.  
**Cytogenetics:** Normal.

### NEL task

Recognise a characteristic possible germline-plus-somatic DDX41 architecture, avoid assigning phase, and state counselling, constitutional-testing and donor implications.

### Marking criteria

- **R1C1:** Preserve the supplied MDS diagnosis and qualify it with **possible germline DDX41 predisposition**.
- **R2C1:** Keep any disease-specific DDX41 prognostic statement separate from IPSS-M and conditional on constitutional confirmation.
- **R5C1:** Flag the 48% loss-of-function variant as possible/presumed germline pending confirmation and the 9% R525H as compatible with an acquired second event. Recommend counselling, constitutional testing and related-donor review.

## Case 8B — Isolated low-VAF DDX41 R525H

### Clinical information

Marrow shows hypocellular MDS with low blasts and multilineage dysplasia.

**NGS:** `DDX41` p.(Arg525His), VAF 8%.  
**Cytogenetics:** Normal.

### NEL task

Recognise that absence of a near-heterozygous DDX41 variant on the myeloid panel does not exclude germline predisposition when a recurrent somatic second event is present.

### Marking criteria

- **R5C1:** State that low-VAF DDX41 R525H is compatible with a somatic clone but can justify dedicated constitutional DDX41 analysis, including copy-number assessment.
- **R5C2:** Recommend genetic counselling and dedicated constitutional DDX41 analysis in a validated non-haematopoietic specimen.

## Case 8C — CEBPA-defined AML with possible germline architecture

### Clinical information

Marrow shows AML with 40% blasts.

**NGS:** `CEBPA` N-terminal truncating variant, VAF 44%; `CEBPA` in-frame bZIP variant, VAF 46%.  
**Cytogenetics:** Normal.

### NEL task

Assign the CEBPA-defined AML entity, apply the relevant ELN category, and flag possible germline CEBPA without inferring phase or identifying the constitutional allele from bulk VAF.

### Marking criteria

- **R1C1:** State **AML with CEBPA mutation** because the in-frame bZIP alteration is the qualifying lesion.
- **R2C1:** Apply ELN 2022 and assign the applicable favourable category.
- **R1C2/R5C1:** Two variants at 44% and 46% VAF trigger possible germline CEBPA review. Recommend counselling and constitutional testing.

---

# Case 9 — CNL versus MDS/MPN with neutrophilia

## Shared stem

70M with persistent neutrophilic leukocytosis. BCR::ABL1 and PDGFRA, PDGFRB, FGFR1 and PCM1::JAK2 rearrangements are negative. Variant-specific morphology and counts are supplied below.

## Case 9A — CSF3R-driven CNL

### Clinical information

WCC 34 × 10^9/L, mature neutrophils 88%, circulating myeloid precursors under 2%, no dysgranulopoiesis, monocytes and basophils below exclusion thresholds. Marrow and clinical review establish **chronic neutrophilic leukaemia** after exclusion of reactive neutrophilia.

**NGS:** `CSF3R` p.(Thr618Ile), VAF 42%.  
**Cytogenetics:** Normal.

### NEL task

Confirm the supplied CNL diagnosis with its defining molecular driver, report its molecular actionability, and avoid constructing a complete clinical risk score.

### Marking criteria

- **R1C1:** Confirm **CNL**; CSF3R T618I is diagnostic support in the supplied clinicomorphological context.
- **R3C1:** State that JAK-pathway inhibition may be considered on the basis of CSF3R T618I, with response uncertainty acknowledged.

## Case 9B — MDS/MPN with neutrophilia

### Clinical information

WCC 28 × 10^9/L, circulating myeloid precursors 14%, prominent dysgranulopoiesis, qualifying cytopenia, monocytes and basophils below exclusion thresholds. Marrow and clinical review establish **MDS/MPN with neutrophilia**. CSF3R pathogenic variants are not detected.

**NGS:** `SETBP1` p.(Asp868Asn), VAF 30%; `ASXL1` p.(Gly646TrpfsTer12), VAF 28%; `ETNK1` p.(Gly82Arg), VAF 18%.  
**Cytogenetics:** Normal.

### NEL task

Support the supplied diagnosis without treating SETBP1 as independently diagnostic, interpret the exact ETNK1 variant rather than the gene name alone, and avoid CSF3R-based actionability.

### Marking criteria

- **R1C1:** Confirm **MDS/MPN with neutrophilia** in the supplied morphology. SETBP1 is supportive, not independently diagnostic.

## Case 9C — CNL with adverse co-mutation

### Clinical information

WCC 30 × 10^9/L with mature neutrophilia, low circulating precursors, no dysgranulopoiesis, and qualifying exclusion findings. Marrow and clinical review establish **CNL**.

**NGS:** `CSF3R` p.(Thr618Ile), VAF 40%; `SETBP1` p.(Asp868Asn), VAF 26%; `ASXL1` p.(Gly646TrpfsTer12), VAF 22%.  
**Cytogenetics:** Normal.

### NEL task

Preserve the CNL diagnosis despite co-mutations, report the disease-specific ASXL1 prognostic contribution without a full score, and avoid claiming that ASXL1 or SETBP1 predicts treatment response.

### Marking criteria

- **R1C1:** Confirm **CNL**; co-mutations do not displace the CSF3R-defined diagnosis in the supplied morphology.
- **R2C1:** Report ASXL1 as an adverse molecular contribution under the relevant CNL model.
- **R3C1:** Link potential ruxolitinib use to CSF3R T618I, not to SETBP1 or ASXL1.

---

# Case 10 — del(5q) MDS and TP53 escalation

## Shared stem

68F with transfusion-dependent anaemia. Marrow shows a myelodysplastic neoplasm with del(5q)-type morphology. TP53 findings and blast percentage vary by case.

## Case 10A — Negative NGS control

### Clinical information

Marrow blasts 3%. Cytogenetics show isolated del(5q). Myeloid NGS detects no pathogenic variants.

### NEL task

Show that a negative panel does not alter an explicitly supplied cytogenetically defined diagnosis and does not justify inventing an adverse molecular contribution.

### Marking criteria

- **R1C1:** Preserve **MDS with low blasts and isolated del(5q)**. A negative SNV/indel panel does not negate the cytogenetic diagnosis.
- **R2C1:** State that no TP53-multihit molecular feature is identified.

## Case 10B — Small monoallelic TP53 clone

### Clinical information

Marrow blasts 3%. Cytogenetics show isolated del(5q), with no 17p loss.

**NGS:** `TP53` p.(Arg248Trp), VAF 8%.

### NEL task

Preserve the del(5q) entity, distinguish a small monoallelic TP53 clone from multi-hit disease, and avoid deterministic treatment-resistance claims.

### Marking criteria

- **R1C1:** State **MDS with low blasts and isolated del(5q), with a small monoallelic TP53 clone**; do not call MDS-biTP53.
- **R2C1:** Interpret the TP53 finding as monoallelic rather than TP53-multihit disease.
- **R3C1:** The clone may warrant surveillance but does not by itself prove lenalidomide resistance or mandate a specific treatment strategy.

## Case 10C — Multi-hit TP53 overrides del(5q)

### Clinical information

Marrow blasts 8%. Cytogenetics show a complex karyotype including del(5q).

**NGS:** `TP53` p.(Arg175His), VAF 30%; `TP53` p.(Arg273Cys), VAF 22%.

### NEL task

Apply TP53 diagnostic precedence, replace the favourable isolated-del(5q) framing, and report the major adverse molecular contribution without prescribing a complete treatment protocol.

### Marking criteria

- **R1C1:** State **MDS with biallelic TP53 inactivation**; this takes precedence over the del(5q) category.
- **R2C1:** Report TP53-multihit as the dominant adverse molecular feature.
- **R3C1:** State that TP53-multihit removes the favourable del(5q) framing and may alter therapeutic strategy, including transplant assessment where clinically appropriate.

---

# Case 11 — AML treatment context and MRD

## Shared stem

71M with acute myeloid leukaemia, normal cytogenetics and clinical unfitness for intensive chemotherapy. Variant and treatment context vary by case.

## Case 11A — IDH1 and NPM1 in an unfit patient

### Clinical information

**NGS:** `IDH1` p.(Arg132Cys), VAF 38%; `NPM1` type A, VAF 40%; `DNMT3A` p.(Arg882His), VAF 42%.

### NEL task

Assign the NPM1 entity, report IDH1-directed frontline actionability in the supplied fitness context, and use NPM1 rather than IDH1 or DNMT3A for MRD.

### Marking criteria

- **R1C1:** State **AML with mutated NPM1**; IDH1 is actionable but not entity-defining.
- **R2C1:** Apply ELN 2022 and assign the applicable favourable category.
- **R3C1:** State the IDH1-directed frontline implication for an older or unfit patient, subject to local approval and access.
- **R4C1:** Use the exact NPM1 mutation as the validated molecular MRD target.

## Case 11B — Treatment-dependent prognostic divergence

### Clinical information

A less-intensive AML regimen is planned. Provisional diagnosis: AML.

**NGS:** `IDH2` p.(Arg172Lys), VAF 40%; `SRSF2` p.(Pro95His), VAF 36%.

### NEL task

Assign AML with myelodysplasia-related molecular features, report materially different intensive and less-intensive prognostic categories, and state IDH2 actionability without treating IDH2 or SRSF2 as stand-alone MRD markers.

### Marking criteria

- **R1C1:** State **AML, myelodysplasia-related**, because SRSF2 is a qualifying MR-gene mutation.
- **R2C1:** Report both materially different categories: the applicable ELN 2022 category and ELN 2024 Less-Intensive category.
- **R3C1:** State the IDH2-directed treatment implication in the appropriate disease phase and jurisdiction.
- **R4C1:** No validated leukaemia-specific molecular MRD marker is supplied. Do not use IDH2 or SRSF2 alone to assign MRD status.

## Case 11C — Routine-panel non-detection is not MRD negativity

### Clinical information

After venetoclax/azacitidine, marrow is in morphologic remission with 2% blasts. A baseline NPM1 mutation is not detected by the current routine myeloid panel, which has a 3% reportable VAF threshold.

**Current NGS:** `IDH1` p.(Arg132His), VAF 4%.

### NEL task

Distinguish routine-panel sensitivity from dedicated NPM1 MRD testing and avoid diagnosing relapse or escalating therapy from residual IDH1 alone.

### Marking criteria

- **R1C1:** State **AML in morphologic remission**; residual IDH1 does not create a new diagnosis.
- **R4C1:** NPM1 non-detection means below the routine assay's 3% threshold, not biological absence or molecular remission.
- **R4C2:** Recommend dedicated high-sensitivity testing for the exact baseline NPM1 mutation.
- **R4C3:** IDH1 is not a stand-alone MRD marker and must not independently establish molecular relapse or trigger treatment escalation.

---

# Case 12 — MDS/MPN with SF3B1 mutation and thrombocytosis

## Shared stem

76M with anaemia, persistent thrombocytosis, marrow erythroid dysplasia, enlarged megakaryocytes, 2% blasts and ring sideroblasts. Provisional diagnosis: **MDS/MPN overlap neoplasm with thrombocytosis**. BCR::ABL1 is negative.

## Case 12A — Classic SF3B1/JAK2 overlap entity

### Clinical information

Ring sideroblasts 24%.

**NGS:** `SF3B1` p.(Lys700Glu), VAF 40%; `JAK2` p.(Val617Phe), VAF 22%.  
**Cytogenetics:** Normal.

### NEL task

Refine the supplied overlap diagnosis to the SF3B1-defined thrombocytosis entity and give only supported disease-specific prognostic commentary.

### Marking criteria

- **R1C1:** State **MDS/MPN with SF3B1 mutation and thrombocytosis**. SF3B1 defines the entity and JAK2 supports the proliferative component.

## Case 12C — Monoallelic TP53 and ASXL1 co-mutations

### Clinical information

Ring sideroblasts 20%.

**NGS:** `SF3B1` p.(Lys700Glu), VAF 41%; `JAK2` p.(Val617Phe), VAF 18%; `TP53` p.(Arg248Gln), VAF 18%; `ASXL1` p.(Gly646TrpfsTer12), VAF 22%.  
**Cytogenetics:** Normal.

### NEL task

Preserve the SF3B1-defined overlap entity, distinguish monoallelic TP53 from multi-hit disease, and describe uncertain disease-specific prognostic effects without importing an MDS-only score.

### Marking criteria

- **R1C1:** State **MDS/MPN with SF3B1 mutation and thrombocytosis**, with TP53 and ASXL1 co-mutations. A single 18% TP53 mutation does not create a TP53-defined entity.
- **R2C1:** State that the disease-specific prognostic significance of TP53 and ASXL1 is uncertain in this entity.

---

# Source notes

- Case content was revised from `cases_summary_final_sol_v3.md`.
- Germline VAF convention:
  - Kraft IL, Godley LA. *Identifying potential germline variants from sequencing hematopoietic malignancies.* Blood. 2020;136:2498–2506. A known predisposition variant detected on tumour-only testing at VAF greater than 0.30 should prompt germline testing.
  - Baliakas P, et al. *Nordic Guidelines for Germline Predisposition to Myeloid Neoplasms in Adults.* HemaSphere. 2019;3:e321. Near-heterozygous VAF of approximately 40–60% or near-homozygous VAF above 90% can suggest germline origin.
  - Li MM, et al. *Points to consider for reporting of germline variation in patients undergoing tumor testing.* Genetics in Medicine. 2020. Heterozygous germline variants are typically detected at 40–60% VAF, but tumour biology can move the observed VAF outside that range.
