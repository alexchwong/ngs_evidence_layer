# NEL Demo Suite

This suite contains the repository's bundled demonstration cases. Runtime retrieval must expose only the selected `Clinical information` section before report completion. `Marking criteria` are evaluator-only until `report-final.md` exists.

# Case 1 — NPM1 changes the integrated diagnosis

## Clinical information

68M, pancytopenic for three months, transfusion dependent. Marrow reported as MDS with 12% blasts on the aspirate, dysplasia in two lineages. Normal karyotype on 20 metaphases.

NGS (myeloid panel, 54 genes):
- NPM1 c.863_864insTCTG p.(Trp288CysfsTer12), VAF 41%
- DNMT3A p.(Arg882His), VAF 46%
- FLT3-ITD, allelic ratio 0.38

## NEL task

Generate the integrated NGS report and determine whether the molecular findings change the provisional disease classification.

## Marking criteria

- The integrated diagnosis should change from provisional MDS when the retrieved NPM1 diagnostic criteria are satisfied.
- NPM1 classification evidence should drive that diagnostic change; FLT3 should not independently redefine the disease merely because it is present.
- The final report should use the revised integrated diagnosis and downstream evidence retrieved for that diagnosis.

---

# Case 2 — SF3B1 refinement without major-category escalation

## Clinical information

Provisional diagnosis: MDS.

74F, macrocytic anaemia, Hb 92 g/L, no transfusion requirement yet. Neutrophils and platelets normal. Marrow: hypercellular, erythroid dysplasia with ring sideroblasts, no excess of blasts. Karyotype normal.

NGS:
- SF3B1 p.(Lys700Glu), VAF 38%
- TET2 p.(Gln1548Ter), VAF 22%
- ASXL1 p.(Gly646TrpfsTer12), VAF 9%

## NEL task

Generate the integrated NGS report and determine whether the molecular findings refine the diagnosis without changing its major category.

## Marking criteria

- The major diagnostic category should remain MDS.
- SF3B1 may support a more specific source-supported MDS label without changing the downstream major category.
- Disease-filtered evidence outside the retained MDS context may appear as suppressed rather than being silently dropped.

---

# Case 3 — Ambiguous myeloid neoplasm

## Clinical information

Provisional diagnosis: myeloid neoplasm, unspecified.

61M, incidental finding. Neutrophils 1.4, Hb 128 g/L, platelets 178. The neutropenia has been present on three counts over eight months. B12, folate, copper, thyroid function, viral serology and autoimmune screen all unremarkable. Marrow: mildly hypocellular for age, no convincing dysplasia, 2% blasts. Normal karyotype.

NGS:
- TET2 p.(Cys1273Tyr), VAF 12%

No other variant above the reporting threshold.

## NEL task

Generate the integrated NGS report while preserving the evidence boundary around an ambiguous provisional diagnosis.

## Marking criteria

- The workflow starts from `myeloid neoplasm, unspecified` and must not upgrade the major category from model knowledge alone.
- Any diagnostic refinement must be supported by retrieved diagnosis evidence and supplied case facts.
- If the corpus does not establish a different diagnosis, the provisional major category should be preserved.

---

# Case 4 — Genes not addressed by the corpus

## Clinical information

57F, known AML, day 28 marrow after intensive induction. Morphological remission.

NGS at diagnosis:
- RUNX1 p.(Arg204Ter), VAF 44%
- SRSF2 p.(Pro95His), VAF 41%
- CSF3R p.(Thr618Ile), VAF 8%
- SETBP1 p.(Asp868Asn), VAF 7%

## NEL task

Generate the integrated NGS report, including any source-supported follow-up-marker implications, without dropping genes that the current corpus cannot assess.

## Marking criteria

- The known major diagnostic category remains AML unless retrieved diagnostic evidence supports a change.
- Every submitted gene should remain visible to the workflow; a gene absent from the corpus should be named as not assessed rather than omitted.
- Follow-up-marker statements in the final report must be limited to biomarker evidence actually retrieved from the current corpus.

---

# Case 5 — DDX41 germline architecture

## Clinical information

Provisional diagnosis: myeloid neoplasm, unspecified.

34M, family history of two first-degree relatives with haematological malignancy in their forties. Presents with cytopenias; marrow shows hypocellularity and mild dysplasia.

NGS:
- DDX41 p.(Met1Ile), VAF 48%
- DDX41 p.(Arg525His), VAF 11%

## NEL task

Generate the integrated NGS report and address germline predisposition only within the supplied facts and retrieved evidence.

## Marking criteria

- Germline-relevant DDX41 evidence should be retrievable by gene when present in the corpus.
- The final report may raise possible germline predisposition only to the extent supported by the evidence block and supplied case facts.
- The two reported VAFs and family history must be preserved without inferring constitutional origin or clonal architecture.

---

# Case 6 — SF3B1 diagnostic adjudication

## Clinical information

Provisional diagnosis: myeloid neoplasm, unspecified.

72F with persistent macrocytic anaemia. Bone marrow is reported as showing insufficient dysplastic change for a diagnosis of MDS. Blasts are not increased. Iron stain shows 7% ring sideroblasts.

NGS (myeloid panel):
- SF3B1 pathogenic variant, VAF 30%

No other case facts relevant to classifier-specific exclusions are supplied.

## NEL task

Generate the integrated NGS report and adjudicate whether source-stated SF3B1 criteria support an MDS diagnosis; fail closed when a required criterion or exclusion is unresolved.

## Marking criteria

- If all source-stated required criteria and exclusions can be satisfied from the supplied facts, the specific label may be `MDS-SF3B1` while the downstream major category is MDS.
- If a required criterion or exclusion is unresolved, adjudication should be indeterminate and preserve `myeloid neoplasm, unspecified` as the downstream major category.
- The workflow must not fill missing classifier-specific exclusions from model knowledge.
