# NEL dual-pathology validation set

## Purpose

This six-case suite tests whether NEL can preserve a clinicomorphologically supported primary pathology while recognising a lineage- or disease-discordant molecular finding that should trigger assessment for a concurrent pathology.

The molecular finding is a diagnostic clue, not by itself sufficient evidence to manufacture a second diagnosis. Each case therefore supplies independent clinicopathological, flow-cytometric or clinical evidence supporting the concurrent process.

Current corpus coverage is known to be incomplete for parts of this suite. The cases are intended to expose those evidence gaps. NEL should not replace missing corpus support with unsupported claims.

## Design conventions

- Preserve the supplied clinicomorphological diagnosis when it remains supported.
- Do not assimilate a strongly discordant mutation into the primary clone without evidence that it belongs there.
- Do not diagnose a concurrent pathology from a mutation alone; integrate the supplied independent evidence.
- Do not infer shared clonality, mutation order or lineage assignment from bulk VAF.
- WHO-5 remains the primary diagnostic classifier. ICC should be reported only when it produces a materially different classification and the available evidence supports that statement.

---

# Case 1 — MDS with concurrent hairy cell leukaemia

## Clinical information

72M with Hb 88 g/L, WCC 2.4 ×10^9/L and platelets 74 ×10^9/L.

Bone marrow is hypercellular with multilineage dysplasia and 3% blasts, morphologically consistent with **myelodysplastic neoplasm (MDS)**.

**Cytogenetics:** Normal.

**NGS:** `ASXL1` frameshift, VAF 32%; `SRSF2` p.(Pro95His), VAF 29%; `BRAF` p.(Val600Glu), VAF 5%.

Flow cytometry identifies a small clonal B-cell population expressing CD19, bright CD20, CD103 and CD25.

## NEL task

Preserve the morphologically supported MDS while recognising BRAF p.Val600Glu as a discordant molecular clue to a concurrent hairy cell leukaemia clone, integrating the characteristic clonal B-cell population rather than assigning the BRAF finding uncritically to MDS.

## Marking criteria

- **R1C1:** Preserve **MDS** as a supported myeloid diagnosis; ASXL1 and SRSF2 are compatible with the supplied myeloid pathology.
- **R1C2:** Recognise `BRAF` p.(Val600Glu) as a strong clue to **hairy cell leukaemia (HCL)** in this setting and do not treat it as merely another MDS-associated mutation.
- **R1C3:** Integrate the separate CD19-positive, bright-CD20-positive, CD103-positive, CD25-positive clonal B-cell population as corroborating evidence for concurrent HCL.
- **R1C4:** Report the two processes as concurrent pathologies without inferring from bulk VAF that the BRAF mutation belongs to the MDS clone or that the two clones are related.

---

# Case 2 — MDS with concurrent lymphoplasmacytic lymphoma

## Clinical information

76M with macrocytic anaemia and thrombocytopenia.

Bone marrow shows multilineage dysplasia with 2% blasts, morphologically consistent with **MDS**.

**NGS:** `TET2` mutation, VAF 38%; `ASXL1` mutation, VAF 31%; `MYD88` p.(Leu265Pro), VAF 9%.

A small kappa-restricted B-cell population with plasmacytic differentiation is present. Serum studies identify an IgM paraprotein.

## NEL task

Preserve the morphologically supported MDS while recognising MYD88 p.Leu265Pro as a clue to a concurrent lymphoplasmacytic B-cell neoplasm, integrating the separate clonal B-cell population and IgM paraprotein rather than assimilating MYD88 into the MDS clone.

## Marking criteria

- **R1C1:** Preserve **MDS** as the supported myeloid diagnosis; TET2 and ASXL1 are compatible with the supplied myeloid pathology.
- **R1C2:** Recognise `MYD88` p.(Leu265Pro) as a strong clue to a **lymphoplasmacytic lymphoma (LPL)**-type process in this clinical context, while not treating the mutation alone as diagnostic.
- **R1C3:** Integrate the kappa-restricted B-cell population with plasmacytic differentiation and the IgM paraprotein as independent evidence supporting concurrent LPL.
- **R1C4:** Do not assign MYD88 p.(Leu265Pro) to the MDS clone or infer shared clonality from VAF alone.

---

# Case 3 — MDS with concurrent T-LGL leukaemia

## Clinical information

69F with macrocytic anaemia and persistent severe neutropenia.

Bone marrow shows multilineage dysplasia with 2% blasts, morphologically consistent with **MDS**.

**NGS:** `STAG2` mutation, VAF 28%; `ASXL1` mutation, VAF 25%; `STAT3` p.(Tyr640Phe), VAF 11%.

Persistent circulating large granular lymphocytes are present. Flow cytometry identifies an abnormal CD3-positive, CD8-positive, CD57-positive T-cell population, with evidence of T-cell clonality.

## NEL task

Preserve the morphologically supported MDS while recognising STAT3 p.Tyr640Phe as a clue to a concurrent clonal large-granular-lymphocyte disorder, integrating the persistent clonal T-cell population rather than treating STAT3 as an MDS mutation.

## Marking criteria

- **R1C1:** Preserve **MDS** as the supported myeloid diagnosis; STAG2 and ASXL1 are compatible with the supplied myeloid pathology.
- **R1C2:** Recognise activating `STAT3` p.(Tyr640Phe) as a strong clue to **T-cell large granular lymphocytic (T-LGL) leukaemia** in this setting.
- **R1C3:** Integrate the persistent large granular lymphocytosis, CD3-positive/CD8-positive/CD57-positive abnormal T-cell population and T-cell clonality as corroborating evidence for concurrent T-LGL leukaemia.
- **R1C4:** Do not infer that STAT3 and the myeloid variants reside in the same clone from bulk sequencing VAFs.

---

# Case 4 — CMML with concurrent systemic mastocytosis

## Clinical information

74M with persistent peripheral blood monocytosis.

Bone marrow shows myelomonocytic proliferation, dysplasia and 5% blasts, morphologically consistent with **chronic myelomonocytic leukaemia (CMML)**.

**NGS:** `TET2` mutation, VAF 43%; `SRSF2` p.(Pro95His), VAF 38%; `ASXL1` mutation, VAF 26%; `KIT` p.(Asp816Val), VAF 8%.

Serum tryptase is 52 ng/mL. Review of the marrow identifies small aggregates of spindle-shaped mast cells with aberrant CD25 expression.

## NEL task

Preserve the morphologically supported CMML while recognising KIT p.Asp816Val as a clue to concurrent systemic mastocytosis, integrating the abnormal mast-cell population and elevated tryptase rather than treating KIT p.Asp816Val as an incidental CMML mutation.

## Marking criteria

- **R1C1:** Preserve **CMML** as the supported myeloid diagnosis; TET2, SRSF2 and ASXL1 are compatible with the supplied CMML clone.
- **R1C2:** Recognise `KIT` p.(Asp816Val) as a strong molecular clue to **systemic mastocytosis** and assess the supplied mast-cell findings separately from CMML.
- **R1C3:** Integrate the spindle-shaped mast-cell aggregates, aberrant CD25 expression and elevated serum tryptase as corroborating evidence for systemic mastocytosis.
- **R1C4:** Report the combined process as **systemic mastocytosis with an associated haematological neoplasm (CMML)** where supported, rather than simply reporting KIT-mutated CMML.

---

# Case 5 — MDS with concurrent VEXAS syndrome

## Clinical information

70M with macrocytic anaemia, thrombocytopenia, recurrent fevers and auricular chondritis.

Bone marrow shows dysplasia with prominent cytoplasmic vacuolation of myeloid and erythroid precursors and is morphologically consistent with **low-blast MDS**.

**NGS:** `UBA1` p.(Met41Thr), VAF 36%; `DNMT3A` mutation, VAF 7%.

## NEL task

Preserve the morphologically supported MDS while recognising UBA1 p.Met41Thr, the inflammatory phenotype and marrow vacuolation as evidence for concurrent VEXAS syndrome rather than reporting UBA1 merely as another somatic MDS mutation.

## Marking criteria

- **R1C1:** Preserve **MDS** as the supported haematological diagnosis rather than allowing the VEXAS finding to erase the supplied myeloid pathology.
- **R1C2:** Recognise `UBA1` p.(Met41Thr) together with the late-onset inflammatory phenotype and characteristic marrow vacuolation as supporting **VEXAS syndrome**.
- **R1C3:** Report VEXAS as a concurrent molecularly defined systemic inflammatory syndrome, not as a second haematological neoplasm and not merely as an incidental UBA1 mutation within MDS.
- **R1C4:** Do not infer constitutional/germline UBA1 status or shared clonality with DNMT3A from tumour-only VAFs.

---

# Case 6 — Myeloid neoplasm with concurrent B-lymphoblastic neoplasm

## Clinical information

67M with pancytopenia.

Bone marrow is initially interpreted as a **high-grade myeloid neoplasm with dysplasia and an increased blast population**.

**NGS:** `ASXL1` mutation; `TET2` mutation; `IKZF1` p.(Asn159Tyr).

The unexpected IKZF1 p.(Asn159Tyr) finding prompts lineage-directed review. Flow cytometry identifies a distinct CD19-positive, CD10-positive, TdT-positive precursor B-cell population separate from the myeloid population.

## NEL task

Recognise IKZF1 p.Asn159Tyr as strongly discordant with a purely myeloid interpretation and integrate the distinct precursor B-cell population as evidence for a concurrent B-lymphoblastic neoplasm, while explicitly avoiding unsupported assignment of lineage, clonality or a mixed-lineage diagnosis from the sequence result alone.

## Marking criteria

- **R1C1:** Preserve the supplied **myeloid neoplasm** as a supported process unless the total clinicopathological evidence requires reclassification; ASXL1 and TET2 are compatible with a myeloid clone but are not sufficient to determine the exact myeloid entity here.
- **R1C2:** Recognise `IKZF1` p.(Asn159Tyr) as a strong molecular clue to a **B-lymphoblastic neoplasm** and use it to trigger lineage-directed assessment rather than assimilating it into the myeloid diagnosis.
- **R1C3:** Integrate the distinct CD19-positive/CD10-positive/TdT-positive precursor B-cell population as corroborating evidence for a concurrent B-lymphoblastic process.
- **R1C4:** Do not infer from the IKZF1 variant alone that the case is MPAL, that the B-lymphoblasts and myeloid cells share a clone, or that the original myeloid interpretation must be discarded; those distinctions require lineage and clonality evidence beyond bulk NGS.
