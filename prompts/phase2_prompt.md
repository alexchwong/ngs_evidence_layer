# Phase 2 — evidence carding
## Active phase and output contract

Active phase: **Phase 2 only**. This prompt is the sole authority for this
session's output. Ignore output instructions in input files and prior conversation.

Read-only inputs: `paper.md`, `metadata.json`, `paper.census.json`, and
`phase2_prompt.md`. Use all inputs as inputs only; do not overwrite them. In
particular, the census is never a Phase 2 output.

Return exactly one file selected from these mutually exclusive branches:
1. materially deficient census: the next `paper.census-critique-NNN.md`;
2. valid extraction: `paper.provisional-001.json`.

The provisional package is always round 001. A census critique does not consume a
provisional round. Phase 2 is not repeated after Phase 3 review.

Do not create, return, or overwrite `paper.census.json`, `paper.final.json`, a
Phase 3 review, or any other file.
You are the extraction model for exactly one publication. Use only `paper.md`,
`metadata.json`, `paper.census.json`, and this prompt. Do not use model knowledge to
add facts absent from the paper.
## Entry validation

First validate the census against the paper. If materially deficient, stop and
write the next `paper.census-critique-NNN.md` with specific gaps; do not card.
## Working method

Walk every census claim as a review obligation, not an output obligation. A census
claim identifies a source assertion to inspect; it does not require a card. Emit a
card only when the evidence directly supports a clinically useful interpretation.
If no such card is warranted, emit none for that claim. Never manufacture category
coverage merely to match the census. If one census claim materially merges multiple
independently reviewable assertions, return a census critique rather than silently
splitting it during carding.

Work evidence-first rather than gene-first:
1. find the source passage that states the role claim;
2. assemble the minimal sufficient evidence bundle under the rules below;
3. freeze the complete candidate evidence bundle before drafting the interpretation;
4. identify only the role, population, disease, effect, and qualifiers explicitly
   supported by that bundle;
5. create at most one card for each independently useful, directly supported role;
6. include only genes participating in that exact assertion.

Do not union assertions, diseases, populations, or qualifiers across separate
locators merely because they belong to the same census claim. A card's `locator`,
interpretation, diseases, genes, category, and evidence bundle must describe the
same source claim.

### Evidence bundle rules

# Evidence bundle rules

Every card must have exactly one evidence bundle. The bundle must directly support every material assertion in the interpretation using source-verbatim fragments from the paper. A locator is navigation metadata, not evidence.

Preserve every qualifier needed to determine where the claim applies or to prevent clinical misapplication. Do not include methodological detail unless it changes the clinical meaning or strength of the claim. Do not use a bibliographic reference-list entry, a heading alone, unsupported nearby text, or model knowledge as substantive evidence.

For germline content, distinguish established inherited or constitutional status from possible constitutional origin and from a recommendation or indication for germline work-up; a work-up recommendation supports only a conditional interpretation.

Use `contiguous_text` when one coherent contiguous passage is sufficient. Its sole fragment has role `claim` and may contain multiple contiguous sentences. Expand around the explicit role claim only as needed to capture antecedents, scope, population, treatment, comparator, analysis, thresholds, exclusions, direction, or clinical consequence. Stop only when the fragment supports every material element of the interpretation without relying on unquoted context.

Use `composite_text` only when no single coherent passage contains the minimal sufficient evidence. Use two to six independently verbatim fragments. One or more `claim` fragments may jointly support one source assertion; add `scope_heading`, `legend`, or `footnote` fragments only when they provide necessary governing context. Every fragment must contribute material support recorded in `support_map`, and all fragments must have compatible scope. Do not combine separate findings, populations, analyses, classifier branches, or independently useful conclusions. If a fragment is unnecessary, use `contiguous_text`, narrow the interpretation, split the card, or omit it.

A `scope_heading` is valid only when the substantive passage occurs within that heading's section and no intervening heading changes scope. A heading supplies context; it does not establish a role claim by itself.

Use `table_relation` when a table value cannot be interpreted defensibly without its governing labels. Quote each required `column_header`, `row_header`, `cell`, `legend`, and `footnote` as a separate fragment. Preserve all applicable row and column headers, spanning or multi-level headers, and marked legends or footnotes. Omit the card when extraction damage or missing structure leaves the relation ambiguous. Do not replace source labels with model-authored key/value facts.

Map every material assertion in the interpretation to explicit supporting source text in `support_map`. If any assertion is unsupported, expand the bundle, narrow the interpretation, split the card, or omit it. Once sufficient evidence is assembled, do not shorten it merely for concision.

### Clinical reporting gate

# Clinical reporting gate

A clinically useful fact is one that could materially contribute to a concise myeloid NGS report by informing:

- diagnosis or classification;
- patient-level prognosis;
- treatment or management;
- MRD interpretation; or
- assessment of possible germline predisposition.

The fact must apply to the stated disease, molecular finding and clinical context.

Background information is not clinically useful by itself, including prevalence, epidemiology, study methodology, molecular mechanism alone, or descriptive associations without a clinical implication.

A negative or null finding is useful only when its absence or lack of effect is clinically informative.

When several findings support the same clinical conclusion, prefer the clinical conclusion rather than its component statistics.

## Geneless treatment claims

Geneless treatment claims (`genes: []`) use a stricter gate. Retain only claims that establish the usual or default treatment strategy for the stated disease or a routine treatment-defining clinical population, such as suitability for intensive therapy.

The claim must identify a standard regimen, treatment backbone, or standard alternative treatment strategy. Clinical actionability alone is insufficient.

Do not retain geneless claims whose usefulness depends on MRD or treatment response, transplant timing or conditioning, surveillance, clinical-trial eligibility, testing or work-up recommendations, or other downstream management advice.

Do not reclassify an otherwise ineligible geneless claim as `treatment` merely to permit `genes: []`.

### Card content rules

# Card content rules

- One card represents one independently useful, directly supported clinical assertion.
- `genes` contains only genes participating in that assertion.
- `genes: []` is permitted only for geneless `diagnosis` or `treatment` assertions.
- A geneless `diagnosis` card must state an independently useful diagnostic/classification criterion, requirement, exclusion, threshold, or distinction.
- A geneless `treatment` card must satisfy the stricter geneless-treatment gate: it must state what treatment the defined patient population would ordinarily receive, independent of a molecular treatment modifier.
- Standard disease-level treatment backbones and standard alternatives for broad clinical strata are in scope; for example, intensive AML induction for suitable patients or venetoclax-based lower-intensity therapy for patients unsuitable for intensive treatment.
- Clinical actionability alone is insufficient for a geneless `treatment` card.
- `diseases` records exact source-supported clinical applicability; derived ancestors are indexing terms only and do not broaden scope.
- Do not merge distinct assertions merely because they share a gene, disease, category, paragraph, table, or census claim.

## Category entailment

- `diagnosis`: the passage states a molecular, morphologic, clinical, quantitative, or other criterion that defines, supports, excludes, differentiates, or changes a diagnosis or classification.
- `prognosis`: the passage explicitly states an outcome, risk, survival, progression, relapse, or named prognostic-model effect.
- `treatment`: the passage explicitly supports treatment selection, eligibility, standard treatment, sensitivity, resistance, response, or a treatment-specific effect.
- `biomarker`: the passage explicitly assigns a testing, detection, monitoring, or discrimination role that remains independently useful rather than merely relabelling the same diagnostic assertion. The interpretation must name that independent function.
- `germline`: the passage explicitly concerns inherited, constitutional, or predisposition status, or germline evaluation. Preserve the source's certainty; a work-up recommendation does not establish constitutional status.

### Source disease alias policy

A source-stated disease may ground a canonical card disease only when it is already
canonical or exactly matches a reviewed alias in the canonical source-alias file,
ignoring surrounding whitespace and letter case only.

Emit only the canonical target in `diseases`, but preserve the source's actual disease
or population wording in evidence and interpretation. Canonical disease granularity
is intentionally broader than molecular subtype granularity; for example, reviewed
molecular B-ALL subtype names resolve to `B-ALL` rather than becoming separate card
diseases. Do not use fuzzy matching, stemming, punctuation substitution, semantic
inference, or nearest-term mapping. A
source term that is neither canonical nor a configured alias remains outside the
controlled vocabulary.

Canonical source aliases:

```json
{
  "clonal haematopoiesis": "CHIP",
  "clonal haemopoiesis": "CHIP",
  "clonal hematopoiesis": "CHIP",
  "clonal hematopoiesis of indeterminate potential": "CHIP",
  "clonal haematopoiesis of indeterminate potential": "CHIP",
  "clonal haemopoiesis of indeterminate potential": "CHIP",
  "clonal cytopenia of undetermined significance": "CCUS",
  "clonal cytopaenia of undetermined significance": "CCUS",
  "myelodysplastic syndrome": "MDS",
  "myelodysplastic syndromes": "MDS",
  "myelodysplastic neoplasm": "MDS",
  "myelodysplastic neoplasms": "MDS",
  "myelodysplastic syndrome/acute myeloid leukemia": "MDS/AML",
  "myelodysplastic syndrome/acute myeloid leukaemia": "MDS/AML",
  "myelodysplastic neoplasm/acute myeloid leukemia": "MDS/AML",
  "myelodysplastic neoplasm/acute myeloid leukaemia": "MDS/AML",
  "acute myeloid leukemia": "AML",
  "acute myeloid leukaemia": "AML",
  "acute promyelocytic leukemia": "APL",
  "acute promyelocytic leukaemia": "APL",
  "myelodysplastic/myeloproliferative neoplasm": "MDS/MPN",
  "myelodysplastic/myeloproliferative neoplasms": "MDS/MPN",
  "myelodysplastic syndrome/myeloproliferative neoplasm": "MDS/MPN",
  "myelodysplastic/myeloproliferative neoplasm, unclassifiable": "MDS/MPN-U",
  "myelodysplastic/myeloproliferative neoplasm unclassifiable": "MDS/MPN-U",
  "myelodysplastic/myeloproliferative neoplasm, unspecified": "MDS/MPN-U",
  "chronic myelomonocytic leukemia": "CMML",
  "chronic myelomonocytic leukaemia": "CMML",
  "atypical chronic myeloid leukemia": "aCML",
  "atypical chronic myeloid leukaemia": "aCML",
  "atypical chronic myelogenous leukemia": "aCML",
  "atypical chronic myelogenous leukaemia": "aCML",
  "MDS/MPN with neutrophilia": "aCML",
  "myelodysplastic/myeloproliferative neoplasm with neutrophilia": "aCML",
  "MDS/MPN with SF3B1 mutation and thrombocytosis": "MDS/MPN-SF3B1-T",
  "myelodysplastic/myeloproliferative neoplasm with SF3B1 mutation and thrombocytosis": "MDS/MPN-SF3B1-T",
  "MDS/MPN with ring sideroblasts and thrombocytosis": "MDS/MPN-SF3B1-T",
  "myelodysplastic/myeloproliferative neoplasm with ring sideroblasts and thrombocytosis": "MDS/MPN-SF3B1-T",
  "juvenile myelomonocytic leukemia": "JMML",
  "juvenile myelomonocytic leukaemia": "JMML",
  "myeloproliferative neoplasm": "MPN",
  "myeloproliferative neoplasms": "MPN",
  "myeloproliferative neoplasm, unclassifiable": "MPN-U",
  "myeloproliferative neoplasm unclassifiable": "MPN-U",
  "myeloproliferative neoplasm, unspecified": "MPN-U",
  "polycythemia vera": "PV",
  "polycythaemia vera": "PV",
  "polycythemia rubra vera": "PV",
  "polycythaemia rubra vera": "PV",
  "essential thrombocythemia": "ET",
  "essential thrombocythaemia": "ET",
  "primary myelofibrosis": "PMF",
  "post-polycythemia vera myelofibrosis": "post-PV/post-ET MF",
  "post-polycythaemia vera myelofibrosis": "post-PV/post-ET MF",
  "post-essential thrombocythemia myelofibrosis": "post-PV/post-ET MF",
  "post-essential thrombocythaemia myelofibrosis": "post-PV/post-ET MF",
  "post-PV myelofibrosis": "post-PV/post-ET MF",
  "post-ET myelofibrosis": "post-PV/post-ET MF",
  "myeloproliferative neoplasm blast phase": "MPN blast phase",
  "blast-phase myeloproliferative neoplasm": "MPN blast phase",
  "blast phase myeloproliferative neoplasm": "MPN blast phase",
  "chronic myeloid leukemia": "CML",
  "chronic myeloid leukaemia": "CML",
  "chronic myelogenous leukemia": "CML",
  "chronic myelogenous leukaemia": "CML",
  "chronic neutrophilic leukemia": "CNL",
  "chronic neutrophilic leukaemia": "CNL",
  "chronic eosinophilic leukemia": "CEL",
  "chronic eosinophilic leukaemia": "CEL",
  "systemic mastocytosis": "mastocytosis",
  "mast cell neoplasm": "mastocytosis",
  "myeloid/lymphoid neoplasm with eosinophilia and tyrosine kinase fusion": "myeloid/lymphoid neoplasm with eosinophilia and TK fusion",
  "myeloid/lymphoid neoplasms with eosinophilia and tyrosine kinase gene fusions": "myeloid/lymphoid neoplasm with eosinophilia and TK fusion",
  "myeloid/lymphoid neoplasm with eosinophilia and tyrosine kinase gene fusion": "myeloid/lymphoid neoplasm with eosinophilia and TK fusion",
  "blastic plasmacytoid dendritic cell neoplasm": "BPDCN",
  "myeloid neoplasm with germline predisposition": "germline predisposition syndrome",
  "myeloid neoplasm with germ line predisposition": "germline predisposition syndrome",
  "acute leukemia of ambiguous lineage": "acute leukaemia of ambiguous lineage",
  "histiocytic and dendritic cell neoplasm": "histiocytic/dendritic neoplasm",
  "histiocytic and dendritic neoplasm": "histiocytic/dendritic neoplasm",
  "hematological malignancy, other": "haematological malignancy, other",
  "acute lymphoblastic leukemia": "acute lymphoblastic leukaemia/lymphoma",
  "acute lymphoblastic leukaemia": "acute lymphoblastic leukaemia/lymphoma",
  "acute lymphoblastic leukemia/lymphoma": "acute lymphoblastic leukaemia/lymphoma",
  "ALL": "acute lymphoblastic leukaemia/lymphoma",
  "B-lymphoblastic leukaemia/lymphoma": "B-ALL",
  "B-lymphoblastic leukemia/lymphoma": "B-ALL",
  "B-cell acute lymphoblastic leukaemia": "B-ALL",
  "B-cell acute lymphoblastic leukemia": "B-ALL",
  "B lymphoblastic leukaemia/lymphoma": "B-ALL",
  "B lymphoblastic leukemia/lymphoma": "B-ALL",
  "B-lymphoblastic leukaemia/lymphoma, NOS": "B-ALL",
  "B-lymphoblastic leukemia/lymphoma, NOS": "B-ALL",
  "B-lymphoblastic leukaemia/lymphoma with hyperdiploidy": "B-ALL",
  "B-lymphoblastic leukemia/lymphoma with hyperdiploidy": "B-ALL",
  "B-lymphoblastic leukaemia/lymphoma with high hyperdiploidy": "B-ALL",
  "B-lymphoblastic leukemia/lymphoma with high hyperdiploidy": "B-ALL",
  "B-lymphoblastic leukaemia/lymphoma with hypodiploidy": "B-ALL",
  "B-lymphoblastic leukemia/lymphoma with hypodiploidy": "B-ALL",
  "B-lymphoblastic leukaemia/lymphoma with iAMP21": "B-ALL",
  "B-lymphoblastic leukemia/lymphoma with iAMP21": "B-ALL",
  "B-lymphoblastic leukaemia/lymphoma with BCR::ABL1 fusion": "B-ALL",
  "B-lymphoblastic leukemia/lymphoma with BCR::ABL1 fusion": "B-ALL",
  "B-lymphoblastic leukaemia/lymphoma with t(9;22)(q34;q11.2); BCR-ABL1": "B-ALL",
  "B-lymphoblastic leukemia/lymphoma with t(9;22)(q34;q11.2); BCR-ABL1": "B-ALL",
  "B-lymphoblastic leukaemia/lymphoma, BCR-ABL1-like": "B-ALL",
  "B-lymphoblastic leukemia/lymphoma, BCR-ABL1-like": "B-ALL",
  "Philadelphia chromosome-like acute lymphoblastic leukaemia": "B-ALL",
  "Philadelphia chromosome-like acute lymphoblastic leukemia": "B-ALL",
  "Ph-like acute lymphoblastic leukaemia": "B-ALL",
  "Ph-like acute lymphoblastic leukemia": "B-ALL",
  "B-lymphoblastic leukaemia/lymphoma with KMT2A rearrangement": "B-ALL",
  "B-lymphoblastic leukemia/lymphoma with KMT2A rearrangement": "B-ALL",
  "B-lymphoblastic leukaemia/lymphoma with t(v;11q23.3); KMT2A-rearranged": "B-ALL",
  "B-lymphoblastic leukemia/lymphoma with t(v;11q23.3); KMT2A-rearranged": "B-ALL",
  "B-lymphoblastic leukaemia/lymphoma with ETV6::RUNX1 fusion": "B-ALL",
  "B-lymphoblastic leukemia/lymphoma with ETV6::RUNX1 fusion": "B-ALL",
  "B-lymphoblastic leukaemia/lymphoma with t(12;21)(p13.2;q22.1); ETV6-RUNX1": "B-ALL",
  "B-lymphoblastic leukemia/lymphoma with t(12;21)(p13.2;q22.1); ETV6-RUNX1": "B-ALL",
  "B-lymphoblastic leukaemia/lymphoma with ETV6::RUNX1-like features": "B-ALL",
  "B-lymphoblastic leukemia/lymphoma with ETV6::RUNX1-like features": "B-ALL",
  "B-lymphoblastic leukaemia/lymphoma with TCF3::PBX1 fusion": "B-ALL",
  "B-lymphoblastic leukemia/lymphoma with TCF3::PBX1 fusion": "B-ALL",
  "B-lymphoblastic leukaemia/lymphoma with t(1;19)(q23;p13.3); TCF3-PBX1": "B-ALL",
  "B-lymphoblastic leukemia/lymphoma with t(1;19)(q23;p13.3); TCF3-PBX1": "B-ALL",
  "B-lymphoblastic leukaemia/lymphoma with IGH::IL3 fusion": "B-ALL",
  "B-lymphoblastic leukemia/lymphoma with IGH::IL3 fusion": "B-ALL",
  "B-lymphoblastic leukaemia/lymphoma with t(5;14)(q31.1;q32.1); IGH/IL3": "B-ALL",
  "B-lymphoblastic leukemia/lymphoma with t(5;14)(q31.1;q32.1); IGH/IL3": "B-ALL",
  "B-lymphoblastic leukaemia/lymphoma with TCF3::HLF fusion": "B-ALL",
  "B-lymphoblastic leukemia/lymphoma with TCF3::HLF fusion": "B-ALL",
  "B-lymphoblastic leukaemia/lymphoma with other defined genetic abnormalities": "B-ALL",
  "B-lymphoblastic leukemia/lymphoma with other defined genetic abnormalities": "B-ALL",
  "monoclonal B-cell lymphocytosis": "MBL",
  "chronic lymphocytic leukaemia/small lymphocytic lymphoma": "CLL/SLL",
  "chronic lymphocytic leukemia/small lymphocytic lymphoma": "CLL/SLL",
  "chronic lymphocytic leukaemia": "CLL/SLL",
  "chronic lymphocytic leukemia": "CLL/SLL",
  "small lymphocytic lymphoma": "CLL/SLL",
  "hairy cell leukaemia": "HCL",
  "hairy cell leukemia": "HCL",
  "splenic marginal zone lymphoma": "SMZL",
  "splenic diffuse red pulp small B-cell lymphoma": "SDRPL",
  "splenic B-cell lymphoma/leukaemia with prominent nucleoli": "SBLPN",
  "splenic B-cell lymphoma/leukemia with prominent nucleoli": "SBLPN",
  "lymphoplasmacytic lymphoma": "LPL",
  "IgM lymphoplasmacytic lymphoma": "IgM LPL/WM",
  "IgM lymphoplasmacytic lymphoma/Waldenström macroglobulinaemia": "IgM LPL/WM",
  "IgM lymphoplasmacytic lymphoma/Waldenstrom macroglobulinemia": "IgM LPL/WM",
  "Waldenström macroglobulinaemia": "IgM LPL/WM",
  "Waldenström macroglobulinemia": "IgM LPL/WM",
  "Waldenstrom macroglobulinemia": "IgM LPL/WM",
  "WM": "IgM LPL/WM",
  "non-IgM lymphoplasmacytic lymphoma": "non-IgM LPL",
  "extranodal marginal zone lymphoma of mucosa-associated lymphoid tissue": "extranodal MZL of MALT",
  "extranodal marginal zone lymphoma of mucosa associated lymphoid tissue": "extranodal MZL of MALT",
  "MALT lymphoma": "extranodal MZL of MALT",
  "primary cutaneous marginal zone lymphoma": "primary cutaneous MZL",
  "nodal marginal zone lymphoma": "NMZL",
  "paediatric marginal zone lymphoma": "paediatric MZL",
  "pediatric marginal zone lymphoma": "paediatric MZL",
  "FL": "follicular lymphoma",
  "in situ follicular neoplasia": "in situ follicular B-cell neoplasm",
  "paediatric type follicular lymphoma": "paediatric-type follicular lymphoma",
  "pediatric-type follicular lymphoma": "paediatric-type follicular lymphoma",
  "pediatric type follicular lymphoma": "paediatric-type follicular lymphoma",
  "duodenal type follicular lymphoma": "duodenal-type follicular lymphoma",
  "primary cutaneous follicle center lymphoma": "primary cutaneous follicle centre lymphoma",
  "in situ mantle cell neoplasia": "in situ mantle cell neoplasm",
  "MCL": "mantle cell lymphoma",
  "leukemic non-nodal mantle cell lymphoma": "leukaemic non-nodal mantle cell lymphoma",
  "DLBCL": "DLBCL, NOS",
  "diffuse large B-cell lymphoma, not otherwise specified": "DLBCL, NOS",
  "diffuse large B-cell lymphoma, NOS": "DLBCL, NOS",
  "T-cell/histiocyte-rich large B-cell lymphoma": "THRLBCL",
  "diffuse large B-cell lymphoma/high-grade B-cell lymphoma with MYC and BCL2 rearrangements": "DLBCL/HGBL-MYC/BCL2",
  "diffuse large B-cell lymphoma/high grade B-cell lymphoma with MYC and BCL2 rearrangements": "DLBCL/HGBL-MYC/BCL2",
  "DLBCL/HGBL with MYC and BCL2 rearrangements": "DLBCL/HGBL-MYC/BCL2",
  "large B-cell lymphoma/high-grade B-cell lymphoma with MYC and BCL2 rearrangements": "DLBCL/HGBL-MYC/BCL2",
  "large B-cell lymphoma/high grade B-cell lymphoma with MYC and BCL2 rearrangements": "DLBCL/HGBL-MYC/BCL2",
  "high-grade B-cell lymphoma with 11q aberrations": "HGBL-11q",
  "high-grade B-cell lymphoma with 11q aberration": "HGBL-11q",
  "Burkitt-like lymphoma with 11q aberration": "HGBL-11q",
  "EBV-positive diffuse large B-cell lymphoma": "EBV-positive DLBCL",
  "EBV-positive diffuse large B-cell lymphoma, NOS": "EBV-positive DLBCL",
  "diffuse large B-cell lymphoma associated with chronic inflammation": "DLBCL associated with chronic inflammation",
  "primary cutaneous diffuse large B-cell lymphoma, leg type": "primary cutaneous DLBCL, leg type",
  "PMBCL": "primary mediastinal large B-cell lymphoma",
  "primary mediastinal B-cell lymphoma": "primary mediastinal large B-cell lymphoma",
  "high-grade B-cell lymphoma, NOS": "HGBL, NOS",
  "high grade B-cell lymphoma, NOS": "HGBL, NOS",
  "HGBL NOS": "HGBL, NOS",
  "BL": "Burkitt lymphoma",
  "PEL": "primary effusion lymphoma",
  "HHV8-positive diffuse large B-cell lymphoma, NOS": "KSHV/HHV8-positive DLBCL",
  "KSHV-positive diffuse large B-cell lymphoma": "KSHV/HHV8-positive DLBCL",
  "HHV8-positive germinotropic lymphoproliferative disorder": "KSHV/HHV8-positive germinotropic lymphoproliferative disorder",
  "KSHV-positive germinotropic lymphoproliferative disorder": "KSHV/HHV8-positive germinotropic lymphoproliferative disorder",
  "CHL": "classic Hodgkin lymphoma",
  "classical Hodgkin lymphoma": "classic Hodgkin lymphoma",
  "NLPHL": "nodular lymphocyte predominant Hodgkin lymphoma",
  "nodular lymphocyte-predominant Hodgkin lymphoma": "nodular lymphocyte predominant Hodgkin lymphoma",
  "nodular lymphocyte predominant B-cell lymphoma": "nodular lymphocyte predominant Hodgkin lymphoma",
  "monoclonal gammopathy of undetermined significance": "MGUS",
  "IgM monoclonal gammopathy of undetermined significance": "IgM MGUS",
  "non-IgM monoclonal gammopathy of undetermined significance": "non-IgM MGUS",
  "monoclonal gammopathy of renal significance": "MGRS",
  "immunoglobulin-related (AL) amyloidosis": "AL amyloidosis",
  "immunoglobulin-related AL amyloidosis": "AL amyloidosis",
  "primary amyloidosis": "AL amyloidosis",
  "mu heavy-chain disease": "mu heavy chain disease",
  "gamma heavy-chain disease": "gamma heavy chain disease",
  "alpha heavy-chain disease": "alpha heavy chain disease",
  "multiple myeloma": "plasma cell myeloma",
  "MM": "plasma cell myeloma",
  "T-lymphoblastic leukaemia/lymphoma": "T-ALL",
  "T-lymphoblastic leukemia/lymphoma": "T-ALL",
  "T-cell acute lymphoblastic leukaemia": "T-ALL",
  "T-cell acute lymphoblastic leukemia": "T-ALL",
  "T-lymphoblastic leukaemia/lymphoma, NOS": "T-ALL, NOS",
  "T-lymphoblastic leukemia/lymphoma, NOS": "T-ALL, NOS",
  "early T-precursor lymphoblastic leukaemia/lymphoma": "ETP-ALL",
  "early T-precursor lymphoblastic leukemia/lymphoma": "ETP-ALL",
  "early T-cell precursor lymphoblastic leukaemia": "ETP-ALL",
  "early T-cell precursor lymphoblastic leukemia": "ETP-ALL",
  "T-prolymphocytic leukaemia": "T-PLL",
  "T-prolymphocytic leukemia": "T-PLL",
  "T-cell large granular lymphocytic leukaemia": "T-LGLL",
  "T-cell large granular lymphocytic leukemia": "T-LGLL",
  "T-LGL leukaemia": "T-LGLL",
  "T-LGL leukemia": "T-LGLL",
  "NK-large granular lymphocytic leukaemia": "NK-LGLL",
  "NK-large granular lymphocytic leukemia": "NK-LGLL",
  "chronic lymphoproliferative disorder of NK cells": "NK-LGLL",
  "adult T-cell leukaemia/lymphoma": "ATLL",
  "adult T-cell leukemia/lymphoma": "ATLL",
  "Sézary syndrome": "Sezary syndrome",
  "aggressive NK-cell leukemia": "aggressive NK-cell leukaemia",
  "cutaneous T-cell lymphoma": "primary cutaneous T-cell lymphoma",
  "CTCL": "primary cutaneous T-cell lymphoma",
  "primary cutaneous CD4-positive small or medium T-cell lymphoproliferative disorder": "primary cutaneous CD4-positive small/medium T-cell lymphoproliferative disorder",
  "primary cutaneous acral CD8-positive T-cell lymphoma": "primary cutaneous acral CD8-positive lymphoproliferative disorder",
  "primary cutaneous CD30-positive T-cell lymphoproliferative disorder: lymphomatoid papulosis": "lymphomatoid papulosis",
  "primary cutaneous CD30-positive T-cell lymphoproliferative disorder: primary cutaneous anaplastic large cell lymphoma": "primary cutaneous anaplastic large cell lymphoma",
  "primary cutaneous gamma-delta T-cell lymphoma": "primary cutaneous gamma/delta T-cell lymphoma",
  "indolent T-cell lymphoproliferative disorder of the gastrointestinal tract": "indolent T-cell lymphoma of the gastrointestinal tract",
  "indolent T-cell lymphoproliferative disorder of the GI tract": "indolent T-cell lymphoma of the gastrointestinal tract",
  "indolent T-cell lymphoma of the GI tract": "indolent T-cell lymphoma of the gastrointestinal tract",
  "indolent NK-cell lymphoproliferative disorder of the GI tract": "indolent NK-cell lymphoproliferative disorder of the gastrointestinal tract",
  "NK-cell enteropathy": "indolent NK-cell lymphoproliferative disorder of the gastrointestinal tract",
  "lymphomatoid gastropathy": "indolent NK-cell lymphoproliferative disorder of the gastrointestinal tract",
  "EATL": "enteropathy-associated T-cell lymphoma",
  "MEITL": "monomorphic epitheliotropic intestinal T-cell lymphoma",
  "HSTCL": "hepatosplenic T-cell lymphoma",
  "ALCL": "anaplastic large cell lymphoma",
  "anaplastic large cell lymphoma, ALK-positive": "ALK-positive anaplastic large cell lymphoma",
  "anaplastic large cell lymphoma, ALK-negative": "ALK-negative anaplastic large cell lymphoma",
  "ALK+ ALCL": "ALK-positive anaplastic large cell lymphoma",
  "ALK- ALCL": "ALK-negative anaplastic large cell lymphoma",
  "BIA-ALCL": "breast implant-associated anaplastic large cell lymphoma",
  "nodal T-follicular helper cell lymphoma": "nodal TFH cell lymphoma",
  "nodal TFH-cell lymphoma": "nodal TFH cell lymphoma",
  "nTFHL": "nodal TFH cell lymphoma",
  "angioimmunoblastic T-cell lymphoma": "nodal TFH cell lymphoma, angioimmunoblastic-type",
  "AITL": "nodal TFH cell lymphoma, angioimmunoblastic-type",
  "nTFHL-AI": "nodal TFH cell lymphoma, angioimmunoblastic-type",
  "follicular T-cell lymphoma": "nodal TFH cell lymphoma, follicular-type",
  "nTFHL-F": "nodal TFH cell lymphoma, follicular-type",
  "nodal peripheral T-cell lymphoma with TFH phenotype": "nodal TFH cell lymphoma, NOS",
  "nTFHL-NOS": "nodal TFH cell lymphoma, NOS",
  "peripheral T-cell lymphoma, not otherwise specified": "peripheral T-cell lymphoma, NOS",
  "PTCL-NOS": "peripheral T-cell lymphoma, NOS",
  "nodal EBV-positive T- and NK-cell lymphoma": "EBV-positive nodal T/NK-cell lymphoma",
  "EBV-positive nodal T- and NK-cell lymphoma": "EBV-positive nodal T/NK-cell lymphoma",
  "extranodal NK/T-cell lymphoma, nasal-type": "extranodal NK/T-cell lymphoma",
  "ENKTL": "extranodal NK/T-cell lymphoma"
}
```

For the provisional package, copy `publication_type` and
`publication_type_basis` verbatim from the census and set
`publication_type_verified_by_phase3` to `false`. Phase 2 does not review,
reclassify, or independently validate publication type.

Write `paper.provisional-001.json`, set its `round` field to `1`, and set `audit` to
null.
Use `metadata.publication_key` as the human-readable card namespace. Assign card IDs
as `<publication_key>-C0001`, `<publication_key>-C0002`, and so on, and use each
exact same ID in its paired evidence bundle. Never construct card IDs from `paper_id`; that
content-derived UUID is used only to preserve paper identity across input artefacts.
Use `diseases` only for exact clinical applicability: include each source-grounded
disease for which the interpretation itself is valid. Do not add broader taxonomy
terms to `diseases` merely because the vocabulary's `umbrella` graph identifies them
as ancestors; doing so would make a disease-specific card eligible for unrelated
cases in downstream retrieval.
For every card, mechanically populate `disease_ancestors` with every direct and
transitive parent reached through the vocabulary's `umbrella` graph, in canonical
vocabulary order, excluding values already present in `diseases`. These are derived
indexing terms, not additional clinical scope, and need not appear in the evidence.
For example, a CMML card has exact `diseases: ["CMML"]` and derived ancestors
`["MDS", "MDS/MPN", "MPN"]`; it does not become generally applicable to MDS or MPN.
Set `diseases_covered` to the exact unique union of the cards' exact `diseases`
arrays only; do not include `disease_ancestors`. Set `genes_covered` to the exact
unique union of all card gene arrays.

## Canonical validation assets

The deterministic validation bundle below includes the canonical
`schema/disease_vocabulary.json` and `schema/ingestion_package_schema.json`. Use
those verbatim files as the disease vocabulary/taxonomy and output schema; do not
reconstruct or maintain a second copy in the validator.
## Exit self-audit

For every card ask: (1) does its paired evidence bundle support every material assertion,
and (2) is it independently useful rather than redundant? Repair all failures and
rerun over the whole package, at most three passes. At the cap, narrow or delete
remaining failures. Do not return internal verdicts and do not claim independent
audit.
For every `claim` fragment, inspect the sentence immediately before and after it in
its source passage. If either sentence materially changes scope, certainty,
direction, eligibility, exception, analysis, or clinical meaning, expand the fragment
or bundle, or narrow, split, or delete the card.

For every `composite_text` bundle, also verify that:
1. every `claim` fragment contributes to the same source assertion;
2. no intervening text changes the population, analysis, comparator, disease scope,
   or conclusion;
3. `support_map` identifies the material contribution of each fragment; and
4. the interpretation does not imply a relationship the source does not state.

Once the evidence passes these checks, do not shorten it merely for concision.
## Deterministic exit validation

The bundle below contains the canonical self-contained validator for this phase.
Recreate every displayed file verbatim under `validation_bundle/` at its displayed
relative path. Do not search for or clone the repository, modify the bundled file,
summarize or reinterpret it, rewrite imports, or substitute another validator.

<!-- BEGIN VERBATIM scripts/phase_validation/phase2.py -->
```python
#!/usr/bin/env python3
"""Deterministic validation for Phase 2 using bundled canonical JSON assets."""
import argparse
import json
import re
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

BUNDLE_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = BUNDLE_ROOT / "schema"


def load_json_asset(filename):
    path = SCHEMA_DIR / filename
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RuntimeError(f"cannot read bundled schema asset {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"invalid bundled JSON asset {path}: {exc}") from exc


PACKAGE_SCHEMA = load_json_asset("ingestion_package_schema.json")
DISEASE_VOCABULARY = load_json_asset("disease_vocabulary.json")
DISEASES = list(DISEASE_VOCABULARY["diseases"])
UMBRELLA = {key: list(parents) for key, parents in DISEASE_VOCABULARY["umbrella"].items()}
if PACKAGE_SCHEMA["$defs"]["disease"]["enum"] != DISEASES:
    raise RuntimeError(
        "bundled ingestion package schema disease enum differs from disease vocabulary"
    )

DISEASE_DEPENDENT_CATEGORIES = {"diagnosis", "prognosis", "treatment", "biomarker"}
GENERIC_INTERPRETATION_PATTERNS = (
    "application remains dependent on the source-stated disease context",
    "does not provide a complete patient-level risk score in this passage",
    "the implication is alteration- and disease-specific and should not be generalized",
    "does not by itself establish germline origin, clonal chronology, or suitability as a stand-alone mrd marker",
)
REFERENCE_ENTRY_RE = re.compile(r"^\s*[-*]?\s*\d{1,4}\.\s+.+\b(?:19|20)\d{2}\s*;", re.IGNORECASE)



def read_json(path, label="JSON"):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {label} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {label} in {path}: {exc}") from exc


def disease_ancestors(diseases):
    requested = set(diseases)
    ancestors = set()
    def visit(disease, path):
        if disease in path:
            cycle = " -> ".join((*path, disease))
            raise ValueError(f"disease umbrella cycle: {cycle}")
        next_path = (*path, disease)
        for parent in UMBRELLA.get(disease, []):
            ancestors.add(parent)
            visit(parent, next_path)
    for disease in requested:
        visit(disease, ())
    ancestors -= requested
    return [disease for disease in DISEASES if disease in ancestors]


def normalise(text, markdown=False):
    text = str(text).replace("\r\n", "\n").replace("\r", "\n")
    if markdown:
        lines = []
        for line in text.splitlines():
            if re.match(r"^\s*\|?(?:\s*:?-+:?\s*\|)+\s*$", line):
                continue
            lines.append(line.replace("|", " "))
        text = "\n".join(lines)
    return re.sub(r"\s+", " ", text).strip()


def schema_errors(document, label="package"):
    errors = sorted(
        Draft202012Validator(PACKAGE_SCHEMA, format_checker=FormatChecker()).iter_errors(document),
        key=lambda error: list(error.absolute_path),
    )
    return [
        f"{label} schema: {'/'.join(str(p) for p in error.absolute_path) or '<root>'}: "
        f"{error.message}" for error in errors
    ]


def validate_package(package, metadata, census, source_text=None, require_final=False):
    errors = schema_errors(package, "package")
    warnings = []
    if errors:
        return errors, warnings, None

    if package["paper_id"] != metadata["paper_id"]:
        errors.append("package paper_id does not match metadata")
    if package["census_entries"] != len(census.get("entries", [])):
        errors.append("package census_entries does not match census")
    if "paper_nickname" in package:
        errors.append("provisional package must not contain paper_nickname")
    if package["round"] == 1 and not require_final:
        if package["publication_type"] != census.get("publication_type"):
            errors.append("first-round package publication_type does not match census")
        if package["publication_type_basis"] != census.get("publication_type_basis"):
            errors.append("first-round package publication_type_basis does not match census")
        if package["publication_type_verified_by_phase3"]:
            errors.append("first-round provisional publication type cannot already be verified")

    card_ids = [card["card_id"] for card in package["cards"]]
    evidence_ids = [evidence["card_id"] for evidence in package["evidence"]]
    if len(card_ids) != len(set(card_ids)):
        errors.append("package contains duplicate card_id values")
    if len(evidence_ids) != len(set(evidence_ids)):
        errors.append("package contains more than one evidence bundle for the same card")
    missing_evidence = sorted(set(card_ids) - set(evidence_ids))
    unknown_evidence = sorted(set(evidence_ids) - set(card_ids))
    if missing_evidence:
        errors.append("cards with no evidence bundle: " + ", ".join(missing_evidence))
    if unknown_evidence:
        errors.append("evidence bundles for unknown cards: " + ", ".join(unknown_evidence))

    prefix = metadata["publication_key"] + "-"
    for card in package["cards"]:
        card_id = card["card_id"]
        if not card_id.startswith(prefix):
            errors.append(f"{card_id}: card_id must begin with {prefix}")
        if card["category"] in DISEASE_DEPENDENT_CATEGORIES and not card["diseases"]:
            errors.append(f"{card_id}: {card['category']} card requires at least one disease")
        interpretation = normalise(card["interpretation"]).lower()
        if any(pattern in interpretation for pattern in GENERIC_INTERPRETATION_PATTERNS):
            warnings.append(f"{card_id}: interpretation contains generic category boilerplate; review direct evidence support")
        if "disease_ancestors" in card:
            expected_ancestors = disease_ancestors(card["diseases"])
            if set(card["disease_ancestors"]) != set(expected_ancestors):
                errors.append(
                    f"{card_id}: disease_ancestors must contain exactly the transitive "
                    f"ancestors {expected_ancestors}"
                )
            overlap = sorted(set(card["diseases"]) & set(card["disease_ancestors"]))
            if overlap:
                errors.append(
                    f"{card_id}: exact diseases and disease_ancestors overlap: "
                    + ", ".join(overlap)
                )

    bundle_texts = {}
    source = normalise(source_text, markdown=True) if source_text is not None else None
    for evidence in package["evidence"]:
        card_id = evidence["card_id"]
        fragments = evidence["fragments"]
        fragment_ids = [fragment["fragment_id"] for fragment in fragments]
        fragment_id_set = set(fragment_ids)
        if len(fragment_ids) != len(fragment_id_set):
            errors.append(f"{card_id}: evidence bundle contains duplicate fragment_id values")
        if sum(len(fragment["quote"].split()) for fragment in fragments) > 400:
            errors.append(f"{card_id}: evidence bundle exceeds 400 words")

        roles = {fragment["role"] for fragment in fragments}
        if evidence["evidence_type"] in {"contiguous_text", "composite_text"} and "claim" not in roles:
            errors.append(f"{card_id}: text evidence requires a claim fragment")
        if evidence["evidence_type"] == "contiguous_text" and fragments[0]["role"] != "claim":
            errors.append(f"{card_id}: contiguous text fragment must have role claim")
        if evidence["evidence_type"] == "table_relation" and "cell" not in roles:
            errors.append(f"{card_id}: table evidence requires at least one cell fragment")

        referenced_ids = {
            fragment_id
            for mapped_ids in evidence["support_map"].values()
            for fragment_id in mapped_ids
        }
        dangling_support = sorted(referenced_ids - fragment_id_set)
        if dangling_support:
            errors.append(f"{card_id}: support_map references unknown fragments: " + ", ".join(dangling_support))

        if evidence["evidence_type"] == "table_relation":
            fragments_by_id = {fragment["fragment_id"]: fragment for fragment in fragments}
            relation_references = set()
            for relation in evidence["table_relations"]:
                relation_references.add(relation["value_fragment_id"])
                relation_references.update(relation["header_fragment_ids"])
                relation_references.update(relation["qualifier_fragment_ids"])
                value = fragments_by_id.get(relation["value_fragment_id"])
                if value and value["role"] != "cell":
                    errors.append(f"{card_id}: table value {value['fragment_id']} must have role cell")
                for header_id in relation["header_fragment_ids"]:
                    header = fragments_by_id.get(header_id)
                    if header and header["role"] not in {"column_header", "row_header"}:
                        errors.append(f"{card_id}: table header {header_id} has invalid role {header['role']}")
                for qualifier_id in relation["qualifier_fragment_ids"]:
                    qualifier = fragments_by_id.get(qualifier_id)
                    if qualifier and qualifier["role"] not in {"legend", "footnote"}:
                        errors.append(f"{card_id}: table qualifier {qualifier_id} has invalid role {qualifier['role']}")
            dangling_relations = sorted(relation_references - fragment_id_set)
            if dangling_relations:
                errors.append(f"{card_id}: table relations reference unknown fragments: " + ", ".join(dangling_relations))

        normalized_fragments = []
        for fragment in fragments:
            fragment_label = f"{card_id}/{fragment['fragment_id']}"
            quote_text = fragment["quote"]
            if REFERENCE_ENTRY_RE.search(quote_text):
                errors.append(f"{fragment_label}: fragment appears to be a bibliographic reference-list entry")
            normalized = normalise(quote_text, markdown=True)
            if source is not None and normalized not in source:
                errors.append(f"{fragment_label}: fragment not found verbatim in paper.md")
            normalized_fragments.append(normalized)
        normalized_bundle = " || ".join(normalized_fragments)
        duplicate = bundle_texts.get(normalized_bundle)
        if duplicate:
            warnings.append(f"{card_id}: evidence is identical to {duplicate}; review independent utility")
        bundle_texts[normalized_bundle] = card_id

    covered_genes = sorted({gene for card in package["cards"] for gene in card["genes"]})
    covered_diseases = sorted({disease for card in package["cards"] for disease in card["diseases"]})
    if sorted(package["genes_covered"]) != covered_genes:
        errors.append("genes_covered does not equal genes represented by cards")
    if sorted(package["diseases_covered"]) != covered_diseases:
        errors.append("diseases_covered does not equal diseases represented by cards")

    audit = package["audit"]
    if require_final and audit is None:
        errors.append("final package requires audit metadata")
    if require_final and not package["publication_type_verified_by_phase3"]:
        errors.append("final package publication type must be verified by Phase 3")
    if not require_final and audit is not None:
        errors.append("provisional package audit must be null")
    if audit is not None:
        if audit["approved_round"] != package["round"]:
            errors.append("audit approved_round does not match package round")
        if audit["audit_model"] == package["extraction_model"]:
            errors.append("audit model must differ from extraction model")
        if audit["extraction_model_reviewed"] != package["extraction_model"]:
            errors.append("extraction_model_reviewed does not match extraction_model")
        if audit["publication_type_verdict"]["verdict"] != "pass":
            errors.append("failed publication_type verdict blocks acceptance")
        if not audit["publication_type_verdict"]["verified_by_phase3"]:
            errors.append("audit must mark publication type as verified by Phase 3")
        verdict_ids = [result["card_id"] for result in audit["results"]]
        if len(verdict_ids) != len(set(verdict_ids)):
            errors.append("audit contains duplicate card verdicts")
        if set(verdict_ids) != set(card_ids):
            errors.append("audit must contain exactly one verdict for every card")
        failed = [result["card_id"] for result in audit["results"] if result["verdict"] == "fail"]
        if failed:
            errors.append("failed cards block acceptance: " + ", ".join(failed))

    report = {
        "cards": len(card_ids),
        "census_entries": len(census.get("entries", [])),
        "ratio": round(len(card_ids) / len(census["entries"]), 2) if census.get("entries") else None,
        "census_claims": len(census.get("entries", [])),
    }
    return errors, warnings, report


def validate_phase_files(*, metadata_path, census_path, source_path, provisional_path):
    metadata = read_json(metadata_path, "metadata")
    census = read_json(census_path, "census")
    provisional = read_json(provisional_path, "provisional package")
    source_text = Path(source_path).read_text(encoding="utf-8")
    package_errors, warnings, report = validate_package(
        provisional, metadata, census, source_text=source_text, require_final=False
    )
    phase_report = {"phase": 2}
    phase_report.update(report or {})
    return [f"provisional: {error}" for error in package_errors], warnings, phase_report


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--census", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--provisional", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        errors, warnings, report = validate_phase_files(
            metadata_path=args.metadata,
            census_path=args.census,
            source_path=args.source,
            provisional_path=args.provisional,
        )
    except (OSError, ValueError) as exc:
        sys.exit(f"PHASE 2 VALIDATION FAILED:\n{exc}")
    if errors:
        sys.exit("PHASE 2 VALIDATION FAILED:\n" + "\n".join(errors))
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(json.dumps({"valid": True, **report}, sort_keys=True))


if __name__ == "__main__":
    main()
```
<!-- END VERBATIM scripts/phase_validation/phase2.py -->

<!-- BEGIN VERBATIM schema/ingestion_package_schema.json -->
```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://local/ngs_evidence_layer/ingestion_package_schema.json",
  "title": "Phase 2 provisional or Phase 4 final evidence package",
  "type": "object",
  "required": [
    "schema_version",
    "paper_id",
    "round",
    "extraction_date",
    "extraction_model",
    "publication_type",
    "publication_type_basis",
    "publication_type_verified_by_phase3",
    "genes_covered",
    "diseases_covered",
    "census_entries",
    "cards",
    "evidence",
    "audit"
  ],
  "additionalProperties": false,
  "properties": {
    "schema_version": {
      "const": "5.0"
    },
    "paper_id": {
      "type": "string",
      "format": "uuid"
    },
    "round": {
      "type": "integer",
      "minimum": 1
    },
    "extraction_date": {
      "type": "string",
      "format": "date"
    },
    "extraction_model": {
      "type": "string",
      "minLength": 1
    },
    "paper_nickname": {
      "type": "string",
      "minLength": 1,
      "maxLength": 120
    },
    "publication_type": {
      "enum": [
        "guideline",
        "consensus statement",
        "primary study",
        "systematic review",
        "narrative review",
        "other"
      ]
    },
    "publication_type_basis": {
      "type": "string",
      "minLength": 1
    },
    "publication_type_verified_by_phase3": {
      "type": "boolean"
    },
    "genes_covered": {
      "type": "array",
      "uniqueItems": true,
      "items": {
        "$ref": "#/$defs/gene"
      }
    },
    "diseases_covered": {
      "type": "array",
      "uniqueItems": true,
      "items": {
        "$ref": "#/$defs/disease"
      }
    },
    "census_entries": {
      "type": "integer",
      "minimum": 0
    },
    "cards": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/card"
      }
    },
    "evidence": {
      "type": "array",
      "items": {
        "$ref": "#/$defs/evidence"
      }
    },
    "audit": {
      "anyOf": [
        {
          "type": "null"
        },
        {
          "$ref": "#/$defs/audit"
        }
      ]
    }
  },
  "$defs": {
    "gene": {
      "type": "string",
      "pattern": "^[A-Z0-9][A-Z0-9\\-]*$"
    },
    "disease": {
      "enum": [
        "CHIP",
        "CCUS",
        "MDS",
        "MDS/AML",
        "AML",
        "APL",
        "MDS/MPN",
        "MDS/MPN-U",
        "CMML",
        "aCML",
        "MDS/MPN-SF3B1-T",
        "JMML",
        "MPN",
        "MPN-U",
        "PV",
        "ET",
        "PMF",
        "post-PV/post-ET MF",
        "MPN blast phase",
        "CML",
        "CNL",
        "CEL",
        "mastocytosis",
        "myeloid/lymphoid neoplasm with eosinophilia and TK fusion",
        "BPDCN",
        "germline predisposition syndrome",
        "myeloid neoplasm, unspecified",
        "lymphoid neoplasm",
        "acute leukaemia of ambiguous lineage",
        "histiocytic/dendritic neoplasm",
        "haematological malignancy, other",
        "acute lymphoblastic leukaemia/lymphoma",
        "B-cell lymphoid neoplasm",
        "precursor B-cell neoplasm",
        "B-ALL",
        "mature B-cell neoplasm",
        "small lymphocytic proliferation",
        "MBL",
        "CLL/SLL",
        "splenic B-cell lymphoma/leukaemia",
        "HCL",
        "SMZL",
        "SDRPL",
        "SBLPN",
        "LPL",
        "IgM LPL/WM",
        "non-IgM LPL",
        "marginal zone lymphoma",
        "extranodal MZL of MALT",
        "primary cutaneous MZL",
        "NMZL",
        "paediatric MZL",
        "in situ follicular B-cell neoplasm",
        "follicular lymphoma",
        "paediatric-type follicular lymphoma",
        "duodenal-type follicular lymphoma",
        "primary cutaneous follicle centre lymphoma",
        "mantle cell neoplasm",
        "in situ mantle cell neoplasm",
        "mantle cell lymphoma",
        "leukaemic non-nodal mantle cell lymphoma",
        "large B-cell lymphoma",
        "DLBCL, NOS",
        "THRLBCL",
        "DLBCL/HGBL-MYC/BCL2",
        "ALK-positive large B-cell lymphoma",
        "large B-cell lymphoma with IRF4 rearrangement",
        "HGBL-11q",
        "lymphomatoid granulomatosis",
        "EBV-positive DLBCL",
        "DLBCL associated with chronic inflammation",
        "fibrin-associated large B-cell lymphoma",
        "fluid overload-associated large B-cell lymphoma",
        "plasmablastic lymphoma",
        "primary large B-cell lymphoma of immune-privileged sites",
        "primary cutaneous DLBCL, leg type",
        "intravascular large B-cell lymphoma",
        "primary mediastinal large B-cell lymphoma",
        "mediastinal grey zone lymphoma",
        "HGBL, NOS",
        "Burkitt lymphoma",
        "KSHV/HHV8-associated B-cell lymphoid neoplasm",
        "primary effusion lymphoma",
        "KSHV/HHV8-positive DLBCL",
        "KSHV/HHV8-positive germinotropic lymphoproliferative disorder",
        "Hodgkin lymphoma",
        "classic Hodgkin lymphoma",
        "nodular lymphocyte predominant Hodgkin lymphoma",
        "plasma cell neoplasm/paraprotein disorder",
        "monoclonal gammopathy",
        "MGUS",
        "cold agglutinin disease",
        "IgM MGUS",
        "non-IgM MGUS",
        "MGRS",
        "monoclonal immunoglobulin deposition disease",
        "AL amyloidosis",
        "heavy chain disease",
        "mu heavy chain disease",
        "gamma heavy chain disease",
        "alpha heavy chain disease",
        "plasma cell neoplasm",
        "plasmacytoma",
        "plasma cell myeloma",
        "plasma cell neoplasm with paraneoplastic syndrome",
        "POEMS syndrome",
        "TEMPI syndrome",
        "AESOP syndrome",
        "T-cell/NK-cell lymphoid neoplasm",
        "precursor T-cell neoplasm",
        "T-ALL",
        "T-ALL, NOS",
        "ETP-ALL",
        "mature T-cell/NK-cell neoplasm",
        "mature T-cell/NK-cell leukaemia",
        "T-PLL",
        "T-LGLL",
        "NK-LGLL",
        "ATLL",
        "Sezary syndrome",
        "aggressive NK-cell leukaemia",
        "primary cutaneous T-cell lymphoma",
        "primary cutaneous CD4-positive small/medium T-cell lymphoproliferative disorder",
        "primary cutaneous acral CD8-positive lymphoproliferative disorder",
        "mycosis fungoides",
        "lymphomatoid papulosis",
        "primary cutaneous anaplastic large cell lymphoma",
        "subcutaneous panniculitis-like T-cell lymphoma",
        "primary cutaneous gamma/delta T-cell lymphoma",
        "primary cutaneous CD8-positive aggressive epidermotropic cytotoxic T-cell lymphoma",
        "primary cutaneous peripheral T-cell lymphoma, NOS",
        "intestinal T-cell/NK-cell lymphoid neoplasm",
        "indolent T-cell lymphoma of the gastrointestinal tract",
        "indolent NK-cell lymphoproliferative disorder of the gastrointestinal tract",
        "enteropathy-associated T-cell lymphoma",
        "monomorphic epitheliotropic intestinal T-cell lymphoma",
        "intestinal T-cell lymphoma, NOS",
        "hepatosplenic T-cell lymphoma",
        "anaplastic large cell lymphoma",
        "ALK-positive anaplastic large cell lymphoma",
        "ALK-negative anaplastic large cell lymphoma",
        "breast implant-associated anaplastic large cell lymphoma",
        "nodal TFH cell lymphoma",
        "nodal TFH cell lymphoma, angioimmunoblastic-type",
        "nodal TFH cell lymphoma, follicular-type",
        "nodal TFH cell lymphoma, NOS",
        "peripheral T-cell lymphoma, NOS",
        "EBV-positive T/NK-cell lymphoma",
        "EBV-positive nodal T/NK-cell lymphoma",
        "extranodal NK/T-cell lymphoma",
        "systemic EBV-positive T-cell lymphoma of childhood"
      ]
    },
    "citation": {
      "type": "object",
      "required": [
        "display"
      ],
      "additionalProperties": false,
      "properties": {
        "authors": {
          "type": "array",
          "items": {
            "type": "string"
          }
        },
        "title": {
          "type": "string"
        },
        "journal": {
          "type": "string"
        },
        "year": {
          "type": "integer",
          "minimum": 1950,
          "maximum": 2100
        },
        "volume": {
          "type": "string"
        },
        "issue": {
          "type": "string"
        },
        "pages": {
          "type": "string"
        },
        "display": {
          "type": "string",
          "minLength": 1
        },
        "citation_incomplete": {
          "type": "array",
          "uniqueItems": true,
          "items": {
            "type": "string"
          }
        }
      }
    },
    "card": {
      "type": "object",
      "required": [
        "card_id",
        "locator",
        "interpretation",
        "genes",
        "diseases",
        "category",
        "evidence_tier",
        "secondary_citation"
      ],
      "additionalProperties": false,
      "properties": {
        "card_id": {
          "type": "string",
          "minLength": 1
        },
        "locator": {
          "type": "string",
          "minLength": 1
        },
        "interpretation": {
          "type": "string",
          "minLength": 1
        },
        "genes": {
          "type": "array",
          "uniqueItems": true,
          "items": {
            "$ref": "#/$defs/gene"
          }
        },
        "diseases": {
          "type": "array",
          "uniqueItems": true,
          "items": {
            "$ref": "#/$defs/disease"
          }
        },
        "disease_ancestors": {
          "type": "array",
          "uniqueItems": true,
          "items": {
            "$ref": "#/$defs/disease"
          }
        },
        "category": {
          "enum": [
            "diagnosis",
            "prognosis",
            "treatment",
            "biomarker",
            "germline"
          ]
        },
        "evidence_tier": {
          "enum": [
            "guideline criterion",
            "multivariable-adjusted",
            "univariable or descriptive",
            "restated secondary"
          ]
        },
        "secondary_citation": {
          "anyOf": [
            {
              "type": "null"
            },
            {
              "$ref": "#/$defs/citation"
            }
          ]
        }
      },
      "allOf": [
        {
          "if": {
            "properties": {
              "category": {
                "enum": [
                  "diagnosis",
                  "prognosis",
                  "treatment",
                  "biomarker"
                ]
              }
            },
            "required": [
              "category"
            ]
          },
          "then": {
            "properties": {
              "diseases": {
                "minItems": 1
              }
            }
          }
        },
        {
          "if": {
            "properties": {
              "category": {
                "enum": [
                  "prognosis",
                  "biomarker",
                  "germline"
                ]
              }
            },
            "required": [
              "category"
            ]
          },
          "then": {
            "properties": {
              "genes": {
                "minItems": 1
              }
            }
          }
        }
      ]
    },
    "fragment": {
      "type": "object",
      "required": [
        "fragment_id",
        "role",
        "quote",
        "locator"
      ],
      "additionalProperties": false,
      "properties": {
        "fragment_id": {
          "type": "string",
          "pattern": "^F[0-9]{2}$"
        },
        "role": {
          "enum": [
            "claim",
            "scope_heading",
            "column_header",
            "row_header",
            "cell",
            "legend",
            "footnote"
          ]
        },
        "quote": {
          "type": "string",
          "minLength": 1
        },
        "locator": {
          "type": "string",
          "minLength": 1
        }
      }
    },
    "support_map": {
      "type": "object",
      "minProperties": 1,
      "additionalProperties": false,
      "properties": {
        "gene": {
          "$ref": "#/$defs/fragment_ids"
        },
        "disease": {
          "$ref": "#/$defs/fragment_ids"
        },
        "role": {
          "$ref": "#/$defs/fragment_ids"
        },
        "population": {
          "$ref": "#/$defs/fragment_ids"
        },
        "effect": {
          "$ref": "#/$defs/fragment_ids"
        },
        "qualifier": {
          "$ref": "#/$defs/fragment_ids"
        }
      }
    },
    "fragment_ids": {
      "type": "array",
      "minItems": 1,
      "uniqueItems": true,
      "items": {
        "type": "string",
        "pattern": "^F[0-9]{2}$"
      }
    },
    "table_relation": {
      "type": "object",
      "required": [
        "value_fragment_id",
        "header_fragment_ids",
        "qualifier_fragment_ids"
      ],
      "additionalProperties": false,
      "properties": {
        "value_fragment_id": {
          "type": "string",
          "pattern": "^F[0-9]{2}$"
        },
        "header_fragment_ids": {
          "$ref": "#/$defs/fragment_ids"
        },
        "qualifier_fragment_ids": {
          "type": "array",
          "uniqueItems": true,
          "items": {
            "type": "string",
            "pattern": "^F[0-9]{2}$"
          }
        }
      }
    },
    "evidence": {
      "oneOf": [
        {
          "type": "object",
          "required": [
            "card_id",
            "evidence_type",
            "fragments",
            "support_map"
          ],
          "additionalProperties": false,
          "properties": {
            "card_id": {
              "type": "string",
              "minLength": 1
            },
            "evidence_type": {
              "const": "contiguous_text"
            },
            "fragments": {
              "type": "array",
              "minItems": 1,
              "maxItems": 1,
              "items": {
                "$ref": "#/$defs/fragment"
              }
            },
            "support_map": {
              "$ref": "#/$defs/support_map"
            }
          }
        },
        {
          "type": "object",
          "required": [
            "card_id",
            "evidence_type",
            "fragments",
            "support_map"
          ],
          "additionalProperties": false,
          "properties": {
            "card_id": {
              "type": "string",
              "minLength": 1
            },
            "evidence_type": {
              "const": "composite_text"
            },
            "fragments": {
              "type": "array",
              "minItems": 2,
              "maxItems": 6,
              "items": {
                "$ref": "#/$defs/fragment"
              }
            },
            "support_map": {
              "$ref": "#/$defs/support_map"
            }
          }
        },
        {
          "type": "object",
          "required": [
            "card_id",
            "evidence_type",
            "fragments",
            "support_map",
            "table_relations"
          ],
          "additionalProperties": false,
          "properties": {
            "card_id": {
              "type": "string",
              "minLength": 1
            },
            "evidence_type": {
              "const": "table_relation"
            },
            "fragments": {
              "type": "array",
              "minItems": 2,
              "maxItems": 12,
              "items": {
                "$ref": "#/$defs/fragment"
              }
            },
            "support_map": {
              "$ref": "#/$defs/support_map"
            },
            "table_relations": {
              "type": "array",
              "minItems": 1,
              "items": {
                "$ref": "#/$defs/table_relation"
              }
            }
          }
        }
      ]
    },
    "audit": {
      "type": "object",
      "required": [
        "audit_date",
        "audit_model",
        "extraction_model_reviewed",
        "approved_round",
        "publication_type_verdict",
        "results"
      ],
      "additionalProperties": false,
      "properties": {
        "audit_date": {
          "type": "string",
          "format": "date"
        },
        "audit_model": {
          "type": "string",
          "minLength": 1
        },
        "extraction_model_reviewed": {
          "type": "string",
          "minLength": 1
        },
        "approved_round": {
          "type": "integer",
          "minimum": 1
        },
        "publication_type_verdict": {
          "type": "object",
          "required": [
            "verdict",
            "verified_by_phase3"
          ],
          "additionalProperties": false,
          "properties": {
            "verdict": {
              "enum": [
                "pass",
                "fail"
              ]
            },
            "verified_by_phase3": {
              "const": true
            },
            "reason": {
              "type": "string",
              "minLength": 1
            }
          },
          "allOf": [
            {
              "if": {
                "properties": {
                  "verdict": {
                    "const": "fail"
                  }
                },
                "required": [
                  "verdict"
                ]
              },
              "then": {
                "required": [
                  "reason"
                ]
              }
            }
          ]
        },
        "results": {
          "type": "array",
          "items": {
            "type": "object",
            "required": [
              "card_id",
              "verdict"
            ],
            "additionalProperties": false,
            "properties": {
              "card_id": {
                "type": "string",
                "minLength": 1
              },
              "verdict": {
                "enum": [
                  "pass",
                  "fail"
                ]
              },
              "reason": {
                "type": "string",
                "minLength": 1
              }
            },
            "allOf": [
              {
                "if": {
                  "properties": {
                    "verdict": {
                      "const": "fail"
                    }
                  },
                  "required": [
                    "verdict"
                  ]
                },
                "then": {
                  "required": [
                    "reason"
                  ]
                }
              }
            ]
          }
        }
      }
    }
  }
}
```
<!-- END VERBATIM schema/ingestion_package_schema.json -->

<!-- BEGIN VERBATIM schema/disease_vocabulary.json -->
```json
{
  "vocabulary_version": "1.8",
  "note": "Closed evidence-card disease vocabulary with separate case-only terms, taxonomic umbrellas, and directional category-specific retrieval relationships. Reviewed source-disease aliases are stored separately in schema/source_disease_aliases.json. WHO-HAEM5 lymphoid family/entity terms are included while tumour-like/reactive lesions are excluded. Canonical diseases are kept at clinically useful disease/entity granularity rather than molecular-subtype granularity; source molecular subtype names should resolve through reviewed aliases to the appropriate broader canonical disease. Evidence-card diseases are not to be extended casually: an added term changes what every existing card means by omission.",
  "diseases": [
    "CHIP",
    "CCUS",
    "MDS",
    "MDS/AML",
    "AML",
    "APL",
    "MDS/MPN",
    "MDS/MPN-U",
    "CMML",
    "aCML",
    "MDS/MPN-SF3B1-T",
    "JMML",
    "MPN",
    "MPN-U",
    "PV",
    "ET",
    "PMF",
    "post-PV/post-ET MF",
    "MPN blast phase",
    "CML",
    "CNL",
    "CEL",
    "mastocytosis",
    "myeloid/lymphoid neoplasm with eosinophilia and TK fusion",
    "BPDCN",
    "germline predisposition syndrome",
    "myeloid neoplasm, unspecified",
    "lymphoid neoplasm",
    "acute leukaemia of ambiguous lineage",
    "histiocytic/dendritic neoplasm",
    "haematological malignancy, other",
    "acute lymphoblastic leukaemia/lymphoma",
    "B-cell lymphoid neoplasm",
    "precursor B-cell neoplasm",
    "B-ALL",
    "mature B-cell neoplasm",
    "small lymphocytic proliferation",
    "MBL",
    "CLL/SLL",
    "splenic B-cell lymphoma/leukaemia",
    "HCL",
    "SMZL",
    "SDRPL",
    "SBLPN",
    "LPL",
    "IgM LPL/WM",
    "non-IgM LPL",
    "marginal zone lymphoma",
    "extranodal MZL of MALT",
    "primary cutaneous MZL",
    "NMZL",
    "paediatric MZL",
    "in situ follicular B-cell neoplasm",
    "follicular lymphoma",
    "paediatric-type follicular lymphoma",
    "duodenal-type follicular lymphoma",
    "primary cutaneous follicle centre lymphoma",
    "mantle cell neoplasm",
    "in situ mantle cell neoplasm",
    "mantle cell lymphoma",
    "leukaemic non-nodal mantle cell lymphoma",
    "large B-cell lymphoma",
    "DLBCL, NOS",
    "THRLBCL",
    "DLBCL/HGBL-MYC/BCL2",
    "ALK-positive large B-cell lymphoma",
    "large B-cell lymphoma with IRF4 rearrangement",
    "HGBL-11q",
    "lymphomatoid granulomatosis",
    "EBV-positive DLBCL",
    "DLBCL associated with chronic inflammation",
    "fibrin-associated large B-cell lymphoma",
    "fluid overload-associated large B-cell lymphoma",
    "plasmablastic lymphoma",
    "primary large B-cell lymphoma of immune-privileged sites",
    "primary cutaneous DLBCL, leg type",
    "intravascular large B-cell lymphoma",
    "primary mediastinal large B-cell lymphoma",
    "mediastinal grey zone lymphoma",
    "HGBL, NOS",
    "Burkitt lymphoma",
    "KSHV/HHV8-associated B-cell lymphoid neoplasm",
    "primary effusion lymphoma",
    "KSHV/HHV8-positive DLBCL",
    "KSHV/HHV8-positive germinotropic lymphoproliferative disorder",
    "Hodgkin lymphoma",
    "classic Hodgkin lymphoma",
    "nodular lymphocyte predominant Hodgkin lymphoma",
    "plasma cell neoplasm/paraprotein disorder",
    "monoclonal gammopathy",
    "MGUS",
    "cold agglutinin disease",
    "IgM MGUS",
    "non-IgM MGUS",
    "MGRS",
    "monoclonal immunoglobulin deposition disease",
    "AL amyloidosis",
    "heavy chain disease",
    "mu heavy chain disease",
    "gamma heavy chain disease",
    "alpha heavy chain disease",
    "plasma cell neoplasm",
    "plasmacytoma",
    "plasma cell myeloma",
    "plasma cell neoplasm with paraneoplastic syndrome",
    "POEMS syndrome",
    "TEMPI syndrome",
    "AESOP syndrome",
    "T-cell/NK-cell lymphoid neoplasm",
    "precursor T-cell neoplasm",
    "T-ALL",
    "T-ALL, NOS",
    "ETP-ALL",
    "mature T-cell/NK-cell neoplasm",
    "mature T-cell/NK-cell leukaemia",
    "T-PLL",
    "T-LGLL",
    "NK-LGLL",
    "ATLL",
    "Sezary syndrome",
    "aggressive NK-cell leukaemia",
    "primary cutaneous T-cell lymphoma",
    "primary cutaneous CD4-positive small/medium T-cell lymphoproliferative disorder",
    "primary cutaneous acral CD8-positive lymphoproliferative disorder",
    "mycosis fungoides",
    "lymphomatoid papulosis",
    "primary cutaneous anaplastic large cell lymphoma",
    "subcutaneous panniculitis-like T-cell lymphoma",
    "primary cutaneous gamma/delta T-cell lymphoma",
    "primary cutaneous CD8-positive aggressive epidermotropic cytotoxic T-cell lymphoma",
    "primary cutaneous peripheral T-cell lymphoma, NOS",
    "intestinal T-cell/NK-cell lymphoid neoplasm",
    "indolent T-cell lymphoma of the gastrointestinal tract",
    "indolent NK-cell lymphoproliferative disorder of the gastrointestinal tract",
    "enteropathy-associated T-cell lymphoma",
    "monomorphic epitheliotropic intestinal T-cell lymphoma",
    "intestinal T-cell lymphoma, NOS",
    "hepatosplenic T-cell lymphoma",
    "anaplastic large cell lymphoma",
    "ALK-positive anaplastic large cell lymphoma",
    "ALK-negative anaplastic large cell lymphoma",
    "breast implant-associated anaplastic large cell lymphoma",
    "nodal TFH cell lymphoma",
    "nodal TFH cell lymphoma, angioimmunoblastic-type",
    "nodal TFH cell lymphoma, follicular-type",
    "nodal TFH cell lymphoma, NOS",
    "peripheral T-cell lymphoma, NOS",
    "EBV-positive T/NK-cell lymphoma",
    "EBV-positive nodal T/NK-cell lymphoma",
    "extranodal NK/T-cell lymphoma",
    "systemic EBV-positive T-cell lymphoma of childhood"
  ],
  "case_only_diseases": [
    "no_haematological_malignancy"
  ],
  "case_only_usage": {
    "no_haematological_malignancy": "Use only when the case stem does not specify a haematological malignancy and the NGS result block contains no variants."
  },
  "umbrella": {
    "MDS/AML": [
      "MDS",
      "AML"
    ],
    "APL": [
      "AML"
    ],
    "MDS/MPN": [
      "MDS",
      "MPN"
    ],
    "MDS/MPN-U": [
      "MDS/MPN"
    ],
    "CMML": [
      "MDS/MPN"
    ],
    "aCML": [
      "MDS/MPN"
    ],
    "MDS/MPN-SF3B1-T": [
      "MDS/MPN"
    ],
    "MPN-U": [
      "MPN"
    ],
    "PV": [
      "MPN"
    ],
    "ET": [
      "MPN"
    ],
    "PMF": [
      "MPN"
    ],
    "post-PV/post-ET MF": [
      "MPN"
    ],
    "MPN blast phase": [
      "MPN"
    ],
    "CML": [
      "MPN"
    ],
    "CNL": [
      "MPN"
    ],
    "CEL": [
      "MPN"
    ],
    "JMML": [
      "MPN"
    ],
    "BPDCN": [
      "histiocytic/dendritic neoplasm"
    ],
    "acute lymphoblastic leukaemia/lymphoma": [
      "lymphoid neoplasm"
    ],
    "B-cell lymphoid neoplasm": [
      "lymphoid neoplasm"
    ],
    "precursor B-cell neoplasm": [
      "B-cell lymphoid neoplasm"
    ],
    "B-ALL": [
      "acute lymphoblastic leukaemia/lymphoma",
      "precursor B-cell neoplasm"
    ],
    "mature B-cell neoplasm": [
      "B-cell lymphoid neoplasm"
    ],
    "small lymphocytic proliferation": [
      "mature B-cell neoplasm"
    ],
    "MBL": [
      "small lymphocytic proliferation"
    ],
    "CLL/SLL": [
      "small lymphocytic proliferation"
    ],
    "splenic B-cell lymphoma/leukaemia": [
      "mature B-cell neoplasm"
    ],
    "HCL": [
      "splenic B-cell lymphoma/leukaemia"
    ],
    "SMZL": [
      "splenic B-cell lymphoma/leukaemia"
    ],
    "SDRPL": [
      "splenic B-cell lymphoma/leukaemia"
    ],
    "SBLPN": [
      "splenic B-cell lymphoma/leukaemia"
    ],
    "LPL": [
      "mature B-cell neoplasm"
    ],
    "IgM LPL/WM": [
      "LPL"
    ],
    "non-IgM LPL": [
      "LPL"
    ],
    "marginal zone lymphoma": [
      "mature B-cell neoplasm"
    ],
    "extranodal MZL of MALT": [
      "marginal zone lymphoma"
    ],
    "primary cutaneous MZL": [
      "marginal zone lymphoma"
    ],
    "NMZL": [
      "marginal zone lymphoma"
    ],
    "paediatric MZL": [
      "marginal zone lymphoma"
    ],
    "follicular lymphoma": [
      "mature B-cell neoplasm"
    ],
    "in situ follicular B-cell neoplasm": [
      "follicular lymphoma"
    ],
    "paediatric-type follicular lymphoma": [
      "follicular lymphoma"
    ],
    "duodenal-type follicular lymphoma": [
      "follicular lymphoma"
    ],
    "primary cutaneous follicle centre lymphoma": [
      "mature B-cell neoplasm"
    ],
    "mantle cell neoplasm": [
      "mature B-cell neoplasm"
    ],
    "in situ mantle cell neoplasm": [
      "mantle cell neoplasm"
    ],
    "mantle cell lymphoma": [
      "mantle cell neoplasm"
    ],
    "leukaemic non-nodal mantle cell lymphoma": [
      "mantle cell neoplasm"
    ],
    "large B-cell lymphoma": [
      "mature B-cell neoplasm"
    ],
    "DLBCL, NOS": [
      "large B-cell lymphoma"
    ],
    "THRLBCL": [
      "large B-cell lymphoma"
    ],
    "DLBCL/HGBL-MYC/BCL2": [
      "large B-cell lymphoma"
    ],
    "ALK-positive large B-cell lymphoma": [
      "large B-cell lymphoma"
    ],
    "large B-cell lymphoma with IRF4 rearrangement": [
      "large B-cell lymphoma"
    ],
    "HGBL-11q": [
      "large B-cell lymphoma"
    ],
    "lymphomatoid granulomatosis": [
      "large B-cell lymphoma"
    ],
    "EBV-positive DLBCL": [
      "large B-cell lymphoma"
    ],
    "DLBCL associated with chronic inflammation": [
      "large B-cell lymphoma"
    ],
    "fibrin-associated large B-cell lymphoma": [
      "large B-cell lymphoma"
    ],
    "fluid overload-associated large B-cell lymphoma": [
      "large B-cell lymphoma"
    ],
    "plasmablastic lymphoma": [
      "large B-cell lymphoma"
    ],
    "primary large B-cell lymphoma of immune-privileged sites": [
      "large B-cell lymphoma"
    ],
    "primary cutaneous DLBCL, leg type": [
      "large B-cell lymphoma"
    ],
    "intravascular large B-cell lymphoma": [
      "large B-cell lymphoma"
    ],
    "primary mediastinal large B-cell lymphoma": [
      "large B-cell lymphoma"
    ],
    "mediastinal grey zone lymphoma": [
      "large B-cell lymphoma"
    ],
    "HGBL, NOS": [
      "large B-cell lymphoma"
    ],
    "Burkitt lymphoma": [
      "mature B-cell neoplasm"
    ],
    "KSHV/HHV8-associated B-cell lymphoid neoplasm": [
      "mature B-cell neoplasm"
    ],
    "primary effusion lymphoma": [
      "KSHV/HHV8-associated B-cell lymphoid neoplasm"
    ],
    "KSHV/HHV8-positive DLBCL": [
      "KSHV/HHV8-associated B-cell lymphoid neoplasm"
    ],
    "KSHV/HHV8-positive germinotropic lymphoproliferative disorder": [
      "KSHV/HHV8-associated B-cell lymphoid neoplasm"
    ],
    "Hodgkin lymphoma": [
      "B-cell lymphoid neoplasm"
    ],
    "classic Hodgkin lymphoma": [
      "Hodgkin lymphoma"
    ],
    "nodular lymphocyte predominant Hodgkin lymphoma": [
      "Hodgkin lymphoma"
    ],
    "plasma cell neoplasm/paraprotein disorder": [
      "B-cell lymphoid neoplasm"
    ],
    "monoclonal gammopathy": [
      "plasma cell neoplasm/paraprotein disorder"
    ],
    "MGUS": [
      "monoclonal gammopathy"
    ],
    "IgM MGUS": [
      "MGUS"
    ],
    "non-IgM MGUS": [
      "MGUS"
    ],
    "cold agglutinin disease": [
      "monoclonal gammopathy"
    ],
    "MGRS": [
      "monoclonal gammopathy"
    ],
    "monoclonal immunoglobulin deposition disease": [
      "plasma cell neoplasm/paraprotein disorder"
    ],
    "AL amyloidosis": [
      "monoclonal immunoglobulin deposition disease"
    ],
    "heavy chain disease": [
      "plasma cell neoplasm/paraprotein disorder"
    ],
    "mu heavy chain disease": [
      "heavy chain disease"
    ],
    "gamma heavy chain disease": [
      "heavy chain disease"
    ],
    "alpha heavy chain disease": [
      "heavy chain disease"
    ],
    "plasma cell neoplasm": [
      "plasma cell neoplasm/paraprotein disorder"
    ],
    "plasmacytoma": [
      "plasma cell neoplasm"
    ],
    "plasma cell myeloma": [
      "plasma cell neoplasm"
    ],
    "plasma cell neoplasm with paraneoplastic syndrome": [
      "plasma cell neoplasm"
    ],
    "POEMS syndrome": [
      "plasma cell neoplasm with paraneoplastic syndrome"
    ],
    "TEMPI syndrome": [
      "plasma cell neoplasm with paraneoplastic syndrome"
    ],
    "AESOP syndrome": [
      "plasma cell neoplasm with paraneoplastic syndrome"
    ],
    "T-cell/NK-cell lymphoid neoplasm": [
      "lymphoid neoplasm"
    ],
    "precursor T-cell neoplasm": [
      "T-cell/NK-cell lymphoid neoplasm"
    ],
    "T-ALL": [
      "acute lymphoblastic leukaemia/lymphoma",
      "precursor T-cell neoplasm"
    ],
    "T-ALL, NOS": [
      "T-ALL"
    ],
    "ETP-ALL": [
      "T-ALL"
    ],
    "mature T-cell/NK-cell neoplasm": [
      "T-cell/NK-cell lymphoid neoplasm"
    ],
    "mature T-cell/NK-cell leukaemia": [
      "mature T-cell/NK-cell neoplasm"
    ],
    "T-PLL": [
      "mature T-cell/NK-cell leukaemia"
    ],
    "T-LGLL": [
      "mature T-cell/NK-cell leukaemia"
    ],
    "NK-LGLL": [
      "mature T-cell/NK-cell leukaemia"
    ],
    "ATLL": [
      "mature T-cell/NK-cell leukaemia"
    ],
    "Sezary syndrome": [
      "mature T-cell/NK-cell leukaemia"
    ],
    "aggressive NK-cell leukaemia": [
      "mature T-cell/NK-cell leukaemia"
    ],
    "primary cutaneous T-cell lymphoma": [
      "mature T-cell/NK-cell neoplasm"
    ],
    "primary cutaneous CD4-positive small/medium T-cell lymphoproliferative disorder": [
      "primary cutaneous T-cell lymphoma"
    ],
    "primary cutaneous acral CD8-positive lymphoproliferative disorder": [
      "primary cutaneous T-cell lymphoma"
    ],
    "mycosis fungoides": [
      "primary cutaneous T-cell lymphoma"
    ],
    "lymphomatoid papulosis": [
      "primary cutaneous T-cell lymphoma"
    ],
    "primary cutaneous anaplastic large cell lymphoma": [
      "primary cutaneous T-cell lymphoma"
    ],
    "subcutaneous panniculitis-like T-cell lymphoma": [
      "primary cutaneous T-cell lymphoma"
    ],
    "primary cutaneous gamma/delta T-cell lymphoma": [
      "primary cutaneous T-cell lymphoma"
    ],
    "primary cutaneous CD8-positive aggressive epidermotropic cytotoxic T-cell lymphoma": [
      "primary cutaneous T-cell lymphoma"
    ],
    "primary cutaneous peripheral T-cell lymphoma, NOS": [
      "primary cutaneous T-cell lymphoma"
    ],
    "intestinal T-cell/NK-cell lymphoid neoplasm": [
      "mature T-cell/NK-cell neoplasm"
    ],
    "indolent T-cell lymphoma of the gastrointestinal tract": [
      "intestinal T-cell/NK-cell lymphoid neoplasm"
    ],
    "indolent NK-cell lymphoproliferative disorder of the gastrointestinal tract": [
      "intestinal T-cell/NK-cell lymphoid neoplasm"
    ],
    "enteropathy-associated T-cell lymphoma": [
      "intestinal T-cell/NK-cell lymphoid neoplasm"
    ],
    "monomorphic epitheliotropic intestinal T-cell lymphoma": [
      "intestinal T-cell/NK-cell lymphoid neoplasm"
    ],
    "intestinal T-cell lymphoma, NOS": [
      "intestinal T-cell/NK-cell lymphoid neoplasm"
    ],
    "hepatosplenic T-cell lymphoma": [
      "mature T-cell/NK-cell neoplasm"
    ],
    "anaplastic large cell lymphoma": [
      "mature T-cell/NK-cell neoplasm"
    ],
    "ALK-positive anaplastic large cell lymphoma": [
      "anaplastic large cell lymphoma"
    ],
    "ALK-negative anaplastic large cell lymphoma": [
      "anaplastic large cell lymphoma"
    ],
    "breast implant-associated anaplastic large cell lymphoma": [
      "anaplastic large cell lymphoma"
    ],
    "nodal TFH cell lymphoma": [
      "mature T-cell/NK-cell neoplasm"
    ],
    "nodal TFH cell lymphoma, angioimmunoblastic-type": [
      "nodal TFH cell lymphoma"
    ],
    "nodal TFH cell lymphoma, follicular-type": [
      "nodal TFH cell lymphoma"
    ],
    "nodal TFH cell lymphoma, NOS": [
      "nodal TFH cell lymphoma"
    ],
    "peripheral T-cell lymphoma, NOS": [
      "mature T-cell/NK-cell neoplasm"
    ],
    "EBV-positive T/NK-cell lymphoma": [
      "mature T-cell/NK-cell neoplasm"
    ],
    "EBV-positive nodal T/NK-cell lymphoma": [
      "EBV-positive T/NK-cell lymphoma"
    ],
    "extranodal NK/T-cell lymphoma": [
      "EBV-positive T/NK-cell lymphoma"
    ],
    "systemic EBV-positive T-cell lymphoma of childhood": [
      "EBV-positive T/NK-cell lymphoma"
    ]
  },
  "retrieval_related": {
    "MDS": {
      "diagnosis": [
        "CCUS",
        "CHIP"
      ],
      "prognosis": [
        "CCUS",
        "CHIP"
      ],
      "biomarker": [
        "CCUS",
        "CHIP"
      ]
    },
    "CCUS": {
      "diagnosis": [
        "CHIP",
        "MDS"
      ],
      "prognosis": [
        "CHIP",
        "MDS"
      ],
      "biomarker": [
        "CHIP",
        "MDS"
      ]
    },
    "CHIP": {
      "diagnosis": [
        "CCUS"
      ],
      "biomarker": [
        "CCUS"
      ]
    },
    "MDS/AML": {
      "diagnosis": [
        "MDS",
        "AML"
      ],
      "prognosis": [
        "MDS",
        "AML"
      ],
      "treatment": [
        "MDS",
        "AML"
      ],
      "biomarker": [
        "MDS",
        "AML"
      ]
    },
    "APL": {
      "diagnosis": [
        "AML"
      ],
      "biomarker": [
        "AML"
      ]
    },
    "MDS/MPN": {
      "diagnosis": [
        "MDS",
        "MPN"
      ],
      "prognosis": [
        "MDS",
        "MPN"
      ],
      "treatment": [
        "MDS",
        "MPN"
      ],
      "biomarker": [
        "MDS",
        "MPN"
      ]
    },
    "MDS/MPN-U": {
      "diagnosis": [
        "MDS/MPN",
        "MDS",
        "MPN"
      ],
      "prognosis": [
        "MDS/MPN",
        "MDS",
        "MPN"
      ],
      "treatment": [
        "MDS/MPN",
        "MDS",
        "MPN"
      ],
      "biomarker": [
        "MDS/MPN",
        "MDS",
        "MPN"
      ]
    },
    "CMML": {
      "diagnosis": [
        "MDS/MPN",
        "MDS"
      ],
      "prognosis": [
        "MDS/MPN",
        "MDS"
      ],
      "biomarker": [
        "MDS/MPN",
        "MDS"
      ]
    },
    "aCML": {
      "diagnosis": [
        "MDS/MPN",
        "MPN",
        "CNL"
      ],
      "prognosis": [
        "MDS/MPN",
        "MPN"
      ],
      "treatment": [
        "MDS/MPN",
        "MPN"
      ],
      "biomarker": [
        "MDS/MPN",
        "MPN",
        "CNL"
      ]
    },
    "MDS/MPN-SF3B1-T": {
      "diagnosis": [
        "MDS/MPN",
        "MDS",
        "ET"
      ],
      "prognosis": [
        "MDS/MPN",
        "MDS",
        "ET"
      ],
      "biomarker": [
        "MDS/MPN",
        "MDS",
        "ET"
      ]
    },
    "MPN-U": {
      "diagnosis": [
        "MPN"
      ],
      "prognosis": [
        "MPN"
      ],
      "treatment": [
        "MPN"
      ],
      "biomarker": [
        "MPN"
      ]
    },
    "PV": {
      "diagnosis": [
        "MPN"
      ],
      "prognosis": [
        "MPN"
      ],
      "treatment": [
        "MPN"
      ],
      "biomarker": [
        "MPN"
      ]
    },
    "ET": {
      "diagnosis": [
        "MPN"
      ],
      "prognosis": [
        "MPN"
      ],
      "treatment": [
        "MPN"
      ],
      "biomarker": [
        "MPN"
      ]
    },
    "PMF": {
      "diagnosis": [
        "MPN",
        "post-PV/post-ET MF"
      ],
      "prognosis": [
        "MPN",
        "post-PV/post-ET MF"
      ],
      "biomarker": [
        "MPN",
        "post-PV/post-ET MF"
      ]
    },
    "post-PV/post-ET MF": {
      "diagnosis": [
        "PMF",
        "MPN"
      ],
      "prognosis": [
        "PMF",
        "MPN"
      ],
      "treatment": [
        "PMF",
        "MPN"
      ],
      "biomarker": [
        "PMF",
        "MPN"
      ]
    },
    "MPN blast phase": {
      "diagnosis": [
        "AML",
        "MPN"
      ],
      "prognosis": [
        "AML",
        "MPN"
      ],
      "treatment": [
        "AML",
        "MPN"
      ],
      "biomarker": [
        "AML",
        "MPN"
      ]
    },
    "CNL": {
      "diagnosis": [
        "MPN",
        "aCML"
      ],
      "prognosis": [
        "MPN"
      ],
      "treatment": [
        "MPN"
      ],
      "biomarker": [
        "MPN",
        "aCML"
      ]
    },
    "CEL": {
      "diagnosis": [
        "MPN"
      ],
      "prognosis": [
        "MPN"
      ],
      "treatment": [
        "MPN"
      ],
      "biomarker": [
        "MPN"
      ]
    }
  },
  "categories": [
    "diagnosis",
    "prognosis",
    "treatment",
    "biomarker",
    "germline"
  ],
  "evidence_tiers_strongest_first": [
    "guideline criterion",
    "multivariable-adjusted",
    "univariable or descriptive",
    "restated secondary"
  ],
  "publication_types": [
    "guideline",
    "consensus statement",
    "primary study",
    "systematic review",
    "narrative review",
    "other"
  ],
  "disease_naming_expected": [
    "diagnosis",
    "prognosis",
    "treatment",
    "biomarker"
  ]
}
```
<!-- END VERBATIM schema/disease_vocabulary.json -->
After writing `paper.provisional-001.json`, recreate the bundle and run:
```bash
python validation_bundle/scripts/phase_validation/phase2.py \
  --metadata metadata.json \
  --census paper.census.json \
  --source paper.md \
  --provisional paper.provisional-001.json
```
A non-zero exit means the Phase 2 product is invalid. Repair it and rerun until
successful. Do not edit the output after the successful run. The census-critique
branch has no JSON product validator; its branch and filename checks remain manual.
## Mandatory pre-output gate
Before writing, verify privately that:
1. the active phase is Phase 2 and exactly one allowed output branch applies;
2. the output filename exactly matches that branch and no input file is overwritten;
3. a census critique is Markdown, uses the next three-digit critique number, names
   specific material gaps, and is the only output; or
4. a provisional package conforms to the Phase 2 package schema, its filename round
   equals its `round`, and it contains `cards`, `evidence`, `genes_covered`,
   `diseases_covered`, and `census_entries`;
5. every provisional card has exactly one paired evidence bundle and `audit` is exactly
   `null`;
6. every card ID begins with `metadata.publication_key` plus `-`, no card ID uses
   `paper_id`, and paired card/evidence IDs are identical;
7. every `disease_ancestors` array equals the canonical transitive ancestors of that
   card's exact `diseases`, has no overlap with them, and `genes_covered` and
   `diseases_covered` equal the exact unions represented by cards; and
8. `paper.census.json` was used only as a read-only input.
If any check fails, repair the output before finalizing. Do not print the checklist,
explanatory prose, Markdown fences around JSON, or more than one file.

Return exactly one file with the name required by the selected branch.
