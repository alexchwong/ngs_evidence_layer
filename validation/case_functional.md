# NEL functional reporting validation set

## Purpose

This suite tests explicit NGS reporting functions rather than broad case diversity. It is parallel to `case_summary.md` and does not supersede the existing validation set.

Each numbered group uses a shared design stem with molecular or related test variations. The report-generation model must receive only the shared stem plus the selected variant's clinical information. NEL tasks and marking criteria are evaluator-only.

## Design conventions

- Each pathogenic sequence variant is specified with transcript-level HGVS; fusion/rearrangement findings are specified by the named fusion and transcript form where relevant.
- WHO-5 is the primary diagnostic classifier. ICC is reported when materially different.
- A supplied clinicomorphological diagnosis or diagnostic context is the starting point; genotype must not replace required morphology or history.
- Bulk VAF does not establish zygosity, phase, shared clonality, mutation order, or germline status.
- Tumour-only sequencing must not be used to assign definitive germline status.
- Pending cytogenetics remain pending; do not replace them with the workflow normal-cytogenetics assumption when the case explicitly says they are pending.
- The JAK2 V617F 15% versus 80% cases intentionally benchmark a VAF-associated ET-versus-PMF tendency that is not yet represented in the current corpus. Failure to state that distinction is therefore an expected current corpus limitation, not permission to hallucinate unsupported evidence.

---

# Case 1 — AML functional reporting tests

## Shared stem

Pancytopenia. Marrow shows 30% myeloid blasts. Provisional diagnosis: **acute myeloid leukaemia (AML)**.

## Case 1A — Clonal-haematopoiesis-associated mutations only

### Clinical information

**NGS:** `DNMT3A` NM_022552.5:c.2645G>A, p.(Arg882His), VAF 42%; `TET2` NM_001127208.3:c.1132_1133del, p.(Gly378CysfsTer11), VAF 36%.

**Cytogenetics:** Normal.

### NEL task

Preserve AML, distinguish clonal-haematopoiesis-associated mutations from entity-defining or myelodysplasia-related defining lesions, assign the applicable AML risk category, and avoid treating these variants as stand-alone AML MRD markers.

### Marking criteria

- **R1C1:** Preserve **AML**. DNMT3A R882H and truncating TET2 support clonality but do not independently define another AML entity or AML with myelodysplasia-related genetic abnormalities.
- **R2C1:** Assign **ELN 2022 intermediate risk** from the supplied normal cytogenetics and absence of a favourable- or adverse-defining molecular lesion.
- **R4C1:** Do not promote DNMT3A or TET2 to stand-alone AML MRD markers.

## Case 1B — AML-MR escalation

### Clinical information

**NGS:** `SRSF2` NM_003016.5:c.284C>A, p.(Pro95His), VAF 41%; `ASXL1` NM_015338.6:c.1934dup, p.(Gly646TrpfsTer12), VAF 34%; `TET2` NM_001127208.3:c.1132_1133del, p.(Gly378CysfsTer11), VAF 45%.

**Cytogenetics:** Normal.

### NEL task

Escalate the supplied AML diagnosis to the myelodysplasia-related molecular entity where supported and apply the corresponding AML prognostic implication.

### Marking criteria

- **R1C1:** State **AML, myelodysplasia-related** on the basis of qualifying myelodysplasia-related gene mutation(s), including SRSF2 and ASXL1.
- **R2C1:** Assign **ELN 2022 adverse risk** because of qualifying myelodysplasia-related gene mutation(s).
- **R4C1:** Do not treat the detected SRSF2, ASXL1 or TET2 variants as validated stand-alone AML MRD markers.

## Case 1C — FLT3-ITD

### Clinical information

**NGS:** `FLT3` NM_004119.3:c.1773_1793dup, VAF 32%.

**Cytogenetics:** Normal.

### NEL task

Report the diagnostic limitation, ELN risk effect, treatment actionability and AML-specific MRD implications of an isolated FLT3-ITD.

### Marking criteria

- **R1C1:** Preserve **AML**. FLT3-ITD does not independently define a different WHO-5 AML entity.
- **R2C1:** Assign **ELN 2022 intermediate risk** in the absence of an adverse-risk lesion; do not use FLT3-ITD allelic ratio for ELN 2022 risk assignment.
- **R3C1:** Report FLT3-mutated AML as therapeutically actionable, with treatment setting qualified; first-line intensive therapy may incorporate midostaurin and relapsed/refractory disease may use gilteritinib where appropriate.
- **R4C1:** Recognise FLT3-ITD as a validated high-sensitivity molecular MRD target in AML, while respecting timepoint/assay-specific guidance and its limitations as a sole follow-up marker.

## Case 1D — PML::RARA

### Clinical information

**FISH:** `PML::RARA` rearrangement positive.

**NGS:** `FLT3` NM_004119.3:c.1773_1793dup, VAF 32%; `KRAS` NM_004985.5:c.35G>A, p.(Gly12Asp), VAF 4%.

### NEL task

Recognise the entity-defining PML::RARA result, apply diagnostic precedence, integrate its immediate treatment significance, and prioritise the correct MRD marker over secondary NGS variants.

### Marking criteria

- **R1C1:** Refine the diagnosis to **acute promyelocytic leukaemia with PML::RARA**. PML::RARA takes diagnostic precedence over FLT3-ITD and low-level KRAS.
- **R3C1:** Recognise that PML::RARA has an immediate disease-specific treatment implication even though detected outside the NGS assay.
- **R4C1:** Identify `PML::RARA` as the preferred leukaemia-specific molecular follow-up target; FLT3-ITD or KRAS must not replace it as the principal MRD marker.

## Case 1E — BCR::ABL1 with possible CML blast phase

### Clinical information

**Fusion testing:** `BCR::ABL1` e13a2 (b2a2), p210 transcript detected.

No previous diagnosis of CML is documented. Historical blood counts before this presentation are not available.

**NGS:** No pathogenic or likely pathogenic SNVs or short indels detected.

### NEL task

Recognise BCR::ABL1-positive AML-range disease while explicitly preserving CML blast phase as a competing diagnosis that requires historical correlation.

### Marking criteria

- **R1C1:** State that the current 30% blast presentation with BCR::ABL1 satisfies the blast requirement for **AML with BCR::ABL1** if this is de novo AML.
- **R1C2:** Explicitly report **possible CML blast phase** and recommend correlation with historical blood counts and any prior evidence of chronic-phase CML; the BCR::ABL1 fusion alone must not be treated as proof of de novo AML.
- **R1C3:** Do not downgrade the significance of BCR::ABL1 because the NGS SNV/indel panel is negative; the fusion was established by separate testing.

## Case 1F — Single TP53 mutation, cytogenetics pending

### Clinical information

**NGS:** `TP53` NM_000546.6:c.818G>A, p.(Arg273His), VAF 36%.

**Cytogenetics:** Pending.

### NEL task

Report the TP53-defined ICC implication and adverse biology while keeping TP53 allelic state unresolved until copy-number/cytogenetic assessment is available.

### Marking criteria

- **R1C1:** Preserve an AML diagnosis under WHO-5; a single TP53 mutation does not by itself establish biallelic TP53 inactivation.
- **R1C2:** State the materially different ICC entity **AML with mutated TP53** because blasts are at least 20% and the pathogenic TP53 mutation VAF is above 10%.
- **R1C3:** State that TP53 allelic state remains unresolved while cytogenetic/copy-number assessment is pending; do not infer a second hit from the 36% bulk VAF.
- **R2C1:** Report TP53-mutated AML as having very adverse/poor-risk biology without inventing a resolved multi-hit state.

## Case 1G — TP53 mutation with 17p deletion

### Clinical information

**NGS:** `TP53` NM_000546.6:c.743G>A, p.(Arg248Gln), VAF 48%.

**Cytogenetics/FISH:** del(17p) involving `TP53`.

### NEL task

Recognise the mutation-plus-17p-deletion architecture as multi-hit/biallelic TP53 and report the associated classification and adverse significance.

### Marking criteria

- **R1C1:** State that the TP53 mutation plus deletion of the TP53 locus establishes **multi-hit/biallelic TP53 inactivation**.
- **R1C2:** State the ICC entity **AML with mutated TP53** in this 30% blast case.
- **R2C1:** Report the mutation-plus-17p-deletion architecture as a dominant adverse molecular feature; do not describe TP53 status as monoallelic or unresolved.

## Case 1H — Single CEBPA bZIP in-frame mutation

### Clinical information

**NGS:** `CEBPA` **bZIP in-frame** mutation NM_004364.5:c.937_939dup, p.(Lys313dup), VAF 37%.

**Cytogenetics:** Normal.

No second pathogenic `CEBPA` variant is detected.

### NEL task

Recognise that one explicitly stated in-frame bZIP CEBPA mutation is sufficient for the CEBPA-defined AML entity and favourable ELN category; do not require biallelic CEBPA mutation.

### Marking criteria

- **R1C1:** State **AML with CEBPA mutation / bZIP in-frame CEBPA-mutated AML**. A second CEBPA mutation is not required when the single mutation is explicitly an in-frame bZIP mutation.
- **R2C1:** Assign **ELN 2022 favourable risk** on the basis of the in-frame bZIP CEBPA mutation in the supplied setting.
- **R4C1:** Do not present routine detection/clearance of this CEBPA variant as an established stand-alone molecular MRD strategy; current AML MRD guidance favours flow-based assessment for this subtype.

---

# Case 2 — MDS with 12% blasts functional reporting tests

## Shared stem

Cytopenias and marrow dysplasia are present. Marrow blasts are 12%. Provisional diagnosis: **myelodysplastic neoplasm with increased blasts-2 (MDS-IB2)**.

## Case 2A — No variants, cytogenetics pending

### Clinical information

**NGS:** No pathogenic or likely pathogenic variants detected.

**Cytogenetics:** Pending.

### NEL task

Preserve morphologically established MDS despite negative NGS and keep classification/prognostic limits imposed by pending cytogenetics explicit.

### Marking criteria

- **R1C1:** State **WHO-5 MDS-IB2**. A negative NGS panel does not negate morphologically established MDS.
- **R1C2:** State that under ICC the case lies in the **MDS/AML blast range**, but final genetic subclassification cannot be completed while cytogenetics are pending.
- **R2C1:** Do not assign a complete molecular/cytogenetic prognostic category while required cytogenetic information is unavailable.

## Case 2B — Clonal-haematopoiesis-associated mutations only

### Clinical information

**NGS:** `DNMT3A` NM_022552.5:c.2645G>A, p.(Arg882His), VAF 39%; `TET2` NM_001127208.3:c.1132_1133del, p.(Gly378CysfsTer11), VAF 34%.

**Cytogenetics:** Normal.

### NEL task

Keep the blast-defined MDS diagnosis and avoid treating common clonal-haematopoiesis mutations as an entity-defining molecular escalation.

### Marking criteria

- **R1C1:** State **WHO-5 MDS-IB2**. DNMT3A and TET2 support clonality but do not independently define a different WHO-5 MDS entity.
- **R1C2:** State the ICC blast-range diagnosis without inventing a myelodysplasia-related-gene entity from DNMT3A or TET2.
- **R2C1:** Do not transfer AML-specific or unrelated disease-specific prognostic claims to these variants in MDS.

## Case 2C — NPM1 escalation to AML

### Clinical information

**NGS:** `NPM1` type A, NM_002520.7:c.860_863dup, p.(Trp288CysfsTer12), VAF 38%.

**Cytogenetics:** Normal.

### NEL task

Escalate the provisional MDS diagnosis to NPM1-mutated AML despite the 12% marrow blast count and report the corresponding AML implications.

### Marking criteria

- **R1C1:** Refine the WHO-5 diagnosis to **AML with mutated NPM1**; the NPM1-defined entity is not restricted by the conventional 20% blast threshold in this setting.
- **R1C2:** State the corresponding ICC **AML with mutated NPM1** because the 12% blast count exceeds the ICC minimum for this entity.
- **R2C1:** Assign **ELN 2022 favourable risk** in the supplied setting without an adverse-risk defining finding.
- **R4C1:** Identify the exact NPM1 type A mutation as the preferred dedicated high-sensitivity molecular MRD target.

## Case 2D — Single TP53 mutation, VAF 55%

### Clinical information

**NGS:** `TP53` NM_000546.6:c.818G>A, p.(Arg273His), VAF 55%.

**Cytogenetics/copy-number testing:** No result is yet available.

The NGS assay is tumour-only; constitutional TP53 status has not been established.

### NEL task

Handle a single high-VAF TP53 mutation without converting VAF alone into definitive biallelic or germline status.

### Marking criteria

- **R1C1:** Retain **WHO-5 MDS-IB2** unless biallelic TP53 inactivation is established. A single TP53 mutation at VAF above 50% can raise suspicion for loss of the other allele but is not definitive when copy-number/LOH and constitutional status are unresolved.
- **R1C2:** State the ICC entity **MDS/AML with mutated TP53** because blasts are 10%-19% and the TP53 mutation VAF exceeds 10%.
- **R2C1:** Do not report definitively established multi-hit TP53 prognosis from VAF alone.
- **R5C1:** Do not diagnose germline TP53 status from the 55% tumour-only VAF alone.

## Case 2E — Two TP53 mutations

### Clinical information

**NGS:** `TP53` NM_000546.6:c.743G>A, p.(Arg248Gln), VAF 32%; `TP53` NM_000546.6:c.818G>A, p.(Arg273His), VAF 28%.

**Cytogenetics:** Normal.

### NEL task

Recognise two independent TP53 mutations as multi-hit/biallelic TP53 disease and apply the WHO-5, ICC and prognostic consequences.

### Marking criteria

- **R1C1:** State **WHO-5 MDS with biallelic TP53 inactivation**; two distinct TP53 mutations support multi-hit/biallelic status.
- **R1C2:** State the materially different ICC entity **MDS/AML with mutated TP53**.
- **R2C1:** Report multi-hit TP53 status as the dominant adverse molecular feature.

## Case 2F — RUNX1 germline story

### Clinical information

The patient is 42 years old and reports lifelong thrombocytopenia, usually 70-100 × 10^9/L, with easy bruising predating the current MDS. The patient's mother and sister have longstanding thrombocytopenia, and a maternal uncle developed AML at age 48.

**NGS:** `RUNX1` NM_001754.5:c.496C>T, p.(Arg166Ter), VAF 47%.

The assay is tumour-only. No constitutional specimen has been tested.

### NEL task

Recognise a clinically supported possible germline RUNX1 predisposition from the combination of variant type, VAF, personal phenotype and family history without diagnosing germline status from tumour-only sequencing.

### Marking criteria

- **R1C1:** Preserve the established MDS diagnosis while recognising that constitutional RUNX1 predisposition would be a clinically important disease qualifier rather than a reason to dismiss the acquired neoplasm.
- **R5C1:** Report **suspected/possible germline RUNX1 predisposition** based on the truncating variant plus lifelong platelet phenotype and family history; do not rely on the near-heterozygous VAF alone.
- **R5C2:** Recommend constitutional confirmation using an appropriate non-haematopoietic specimen and genetic counselling; do not call the tumour-only result definitively germline.
- **R5C3:** State relevant family/donor implications conditionally, pending constitutional confirmation.

## Case 2G — DDX41 family history with second-event architecture

### Clinical information

The patient is 68 years old. The patient's father developed MDS at age 71 and a paternal aunt developed AML at age 66.

**NGS:** `DDX41` NM_016222.4:c.415_418dup, p.(Asp140GlyfsTer2), VAF 48%; `DDX41` NM_016222.4:c.1574G>A, p.(Arg525His), VAF 9%.

The assay is tumour-only. No constitutional specimen has been tested.

### NEL task

Recognise a possible germline DDX41 loss-of-function allele with a lower-VAF recurrent second DDX41 event and family history, while avoiding unsupported phase or constitutional claims.

### Marking criteria

- **R5C1:** Report **suspected/possible germline DDX41 predisposition** based on the near-heterozygous truncating variant, lower-VAF DDX41 R525H second-event architecture and family history; VAF alone is insufficient.
- **R5C2:** Do not state that the two DDX41 variants are proven to be in trans, on different clones, or that the 48% allele is definitively constitutional from bulk tumour sequencing.
- **R5C3:** Recommend constitutional confirmation with an appropriate non-haematopoietic specimen and genetic counselling, with donor/family implications expressed conditionally pending confirmation.

---

# Case 3 — Thrombocytosis and leukocytosis without marrow assessment

## Shared stem

Persistent thrombocytosis and leukocytosis. Platelets are 700 × 10^9/L and WCC 14 × 10^9/L. No marrow assessment is available.

## Case 3A — No mutations

### Clinical information

**NGS:** No pathogenic or likely pathogenic variants detected.

### NEL task

Avoid both excluding and diagnosing an MPN from a negative sequencing panel when the required marrow assessment is absent.

### Marking criteria

- **R1C1:** Do not diagnose ET, prefibrotic PMF or overt PMF without the required marrow/clinicopathological criteria.
- **R1C2:** A negative NGS panel does not exclude an MPN; absence of a detected canonical driver does not substitute for marrow assessment.

## Case 3B — CALR

### Clinical information

**NGS:** `CALR` type 1, NM_004343.4:c.1099_1150del, p.(Leu367fs), VAF 42%.

### NEL task

Use CALR type 1 as strong molecular support for an MPN while keeping ET-versus-PMF classification unresolved without marrow morphology.

### Marking criteria

- **R1C1:** State that CALR type 1 strongly supports a **clonal MPN** in this thrombocytosis context.
- **R1C2:** Do not diagnose ET or PMF from CALR alone; marrow morphology is required to distinguish the relevant MPN entities.
- **R2C1:** Do not apply PMF-specific CALR type 1 prognostic effects unless PMF is actually established.

## Case 3C — JAK2 V617F, VAF 15%

### Clinical information

**NGS:** `JAK2` NM_004972.4:c.1849G>T, p.(Val617Phe), VAF 15%.

### NEL task

Report JAK2-supported MPN biology, the lower-VAF pattern that is more compatible with ET than PMF, and the inability to establish a specific MPN without marrow.

### Marking criteria

- **R1C1:** State that JAK2 V617F strongly supports a **clonal MPN** in this clinical context.
- **R1C2:** Recognise that a **15% JAK2 V617F VAF is more compatible with ET than PMF** as a disease-association tendency, while explicitly stating that this does not establish ET and that marrow morphology is still required.
- **R1C3:** Do not infer JAK2 zygosity, mutation order or exact clonal architecture from the 15% bulk VAF.

## Case 3D — JAK2 V617F, VAF 80%

### Clinical information

**NGS:** `JAK2` NM_004972.4:c.1849G>T, p.(Val617Phe), VAF 80%.

### NEL task

Report JAK2-supported MPN biology, the high-VAF pattern that is more compatible with PMF than ET, and the inability to establish a specific MPN without marrow.

### Marking criteria

- **R1C1:** State that JAK2 V617F strongly supports a **clonal MPN** in this clinical context.
- **R1C2:** Recognise that an **80% JAK2 V617F VAF is more compatible with PMF than ET** as a disease-association tendency, while explicitly stating that this does not establish PMF and that marrow morphology is still required.
- **R1C3:** Do not infer JAK2 zygosity, mutation order or exact clonal architecture from the 80% bulk VAF.

## Case 3E — IDH1 without a canonical MPN driver

### Clinical information

**NGS:** `IDH1` NM_005896.4:c.395G>A, p.(Arg132His), VAF 24%. No pathogenic `JAK2`, `CALR` or `MPL` variant is detected.

### NEL task

Recognise clonality without using IDH1 to diagnose an MPN or importing PMF-specific prognosis before PMF is established.

### Marking criteria

- **R1C1:** State that IDH1 supports a clonal myeloid process but is **not a canonical MPN driver** and does not establish ET or PMF without marrow criteria.
- **R1C2:** Absence of JAK2/CALR/MPL does not by itself exclude an MPN.
- **R2C1:** Do not apply PMF-specific adverse prognostic interpretation of IDH1 unless PMF is established.

## Case 3F — NRAS, ASXL1 and monocytosis

### Clinical information

Monocytes are 2.1 × 10^9/L and 15% of the WCC on repeated measurements over 4 months. Reactive causes of monocytosis have been excluded.

**NGS:** `NRAS` NM_002524.5:c.35G>A, p.(Gly12Asp), VAF 31%; `ASXL1` NM_015338.6:c.1934dup, p.(Gly646TrpfsTer12), VAF 35%.

### NEL task

Recognise a CMML-relevant monocytosis-plus-genotype pattern while respecting the absence of marrow assessment and avoiding a genotype-only diagnosis.

### Marking criteria

- **R1C1:** State that the persistent absolute and relative monocytosis plus NRAS/ASXL1 clonal findings **raises CMML as a major competing diagnosis** rather than a straightforward ET/PMF interpretation.
- **R1C2:** Do not treat NRAS or ASXL1 as independently diagnostic of CMML; marrow assessment and full clinicopathological classification remain required.
- **R1C3:** Recognise the proliferative context from WCC >13 × 10^9/L if discussing CMML phenotype, but do not invent a blast-based subgroup without marrow/blast information.

## Case 3G — Possible germline MPL hereditary thrombocytosis

### Clinical information

The patient reports thrombocytosis documented since childhood. The patient's father and two paternal relatives have lifelong thrombocytosis without a documented myeloid neoplasm.

**NGS:** `MPL` NM_005373.3:c.1514G>A, p.(Ser505Asn), VAF 49%.

The assay is tumour-only. No constitutional specimen has been tested.

### NEL task

Recognise possible hereditary MPL-associated thrombocytosis from the variant/phenotype/family-history combination and avoid converting either the MPL result or VAF into a definitive acquired MPN or germline diagnosis.

### Marking criteria

- **R1C1:** Do not diagnose ET or PMF solely from MPL Ser505Asn in a patient without marrow assessment and with a lifelong familial thrombocytosis phenotype.
- **R5C1:** Report **possible/suspected germline MPL-associated hereditary thrombocytosis** based on the specific MPL Ser505Asn variant plus lifelong personal and family phenotype; do not rely on the 49% VAF alone.
- **R5C2:** Recommend constitutional confirmation and genetic counselling; do not state definitive germline status from tumour-only sequencing.

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
