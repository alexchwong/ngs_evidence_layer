# Agreed reporting rules for interpretative myeloid NGS summaries

## Scope and report structure

These rules apply to a concise interpretative summary for clinical haematologists. The purpose is to explain how the detected NGS findings alter or refine the diagnosis, prognosis, management, measurable residual disease assessment or consideration of germline predisposition in the supplied clinical and morphological context.

Use the following order, omitting sections that are not relevant except for the mandatory detected-variant summary:

0. Detected NGS variants
1. Integrated diagnosis and classification
2. Prognostic significance
3. Clinically actionable implications
4. MRD implications
5. Possible germline predisposition

Do not repeat the clinical history, morphology or standard treatment unless needed to explain the effect of a molecular finding.

# R0 — Detected NGS variants

1. **What variants were detected on NGS?** This rule is mandatory and must always be reported. State only the patient-specific NGS result without interpretation. If no pathogenic variants were detected on NGS, state exactly: `No pathogenic variants were detected on NGS.`
<!-- report-audit: classification=REPORT; citation=no_citation_required -->

# R1 — Diagnosis and classification

1. **What WHO-5 diagnosis should the final report state?**
- Use WHO-5 as the primary diagnostic classifier.
- Treat the supplied clinicopathological diagnosis as the starting point.
- Revise the diagnosis when the molecular and clinicopathological criteria establish a different WHO-5 entity.
- Do not diagnose a myeloid neoplasm from mutation number, mutation identity or VAF alone.
- Apply the required blast range, morphology, cytogenetic findings, exact alteration class, VAF threshold and exclusion criteria.
- Do not substitute a biologically related alteration for the required abnormality or use VAF as a substitute for missing diagnostic criteria.

2. **What ICC diagnosis should the final report state, and is it materially different from the WHO-5 diagnosis?**
- Assess ICC separately.
- Do not let the ICC diagnosis replace the primary WHO-5 diagnosis.

3. **What differential diagnoses remain relevant, and which clinical, morphological, cytogenetic or molecular findings favour or exclude each?**
- A genotype may suggest a differential but does not override mandatory clinicopathological criteria.

4. **Does the clinical, morphological, molecular or other laboratory results suggest dual pathology?**
- Consider whether there is strong evidence to support concurrent multiple bone marrow pathologies
- Just because a molecular alteration defines a diagnostic entity, it does not exclude dual pathology.

5. **If morphology does not suggest a primary bone marrow disorder, does the NGS result support CHIP, CCUS or neither?**
- Classify a qualifying clone as CHIP when cytopenia is absent or adequately explained, or CCUS when cytopenia is persistent, otherwise unexplained and no myeloid neoplasm is established.
- If a single variant is detected and that variant is potentially germline, a diagnosis of clonality cannot be made until the possibility of germline origin of this variant is excluded.
- Do not use CHIP or CCUS when a myeloid neoplasm is already established.

6. **Which diagnostic qualifiers or limitations materially affect the diagnosis or differential?**
- Consider informative negative findings, TP53 allelic state, assay limitations, outstanding cytogenetic or fusion studies, and exact variant-level requirements.
- Report only those that change the patient-level interpretation.
- Do not infer phase, clonal architecture or germline origin from bulk VAF alone.


# R2 — Prognostic interpretation

1. **What disease-specific prognostic framework applies, and what risk category can be assigned?**
- Prefer a validated disease-specific prognostic framework where available.
- State the resulting risk category when it can be assigned.
- Assign the complete risk category only when the required inputs are available. For frameworks requiring non-molecular inputs, do not report inability to calculate the score or enumerate missing variables; report relevant molecular contributions under R2.2 instead.
- If the disease is AML:
  - Use ELN 2022 as the primary AML risk classification.
  - Also report ELN 2024 Less-Intensive when it gives a materially different risk category.
  - Reporting ELN 2024 Less-Intensive is mandatory when the patient is receiving less-intensive treatment or is explicitly unsuitable for intensive therapy.
  - ELN 2022 may be omitted when ELN 2024 Less-Intensive is mandatory.
- If no applicable validated prognostic framework exists, classify this rule as OMIT.

2. **What prognostic contribution do the detected NGS variants make within the applicable disease-specific framework?**
- Assess every detected NGS variant against the applicable framework.
- Group variants with the same prognostic effect together.
- Identify variants that contribute favourable or adverse prognostic weight.
- Identify detected variants that do not contribute additional prognostic weight under the framework.
- Do not describe a variant as prognostically neutral merely because it is absent from the framework.
- Do not answer variant-by-variant when multiple variants can be summarised together.

3. **Is there material disease-specific prognostic evidence for any detected variant that is not represented by the applicable framework?**
- Consider reputable disease-specific evidence outside the formal prognostic framework.
- Report only evidence that supports a clinically meaningful prognostic effect.
- Identify the relevant study or evidence source when useful.
- Do not infer a prognostic effect merely because a gene is absent from the framework.
- If an applicable framework exists and there is no material additional prognostic evidence outside it, classify this rule as OMIT.
- If no validated prognostic framework exists, use this rule to report strong disease-specific prognostic evidence.

4. **Does any variant have a different prognostic effect in a relevant differential diagnosis?**
- If a number of morphological differentials exist, evaluate each variant's prognostic value via the relevant disease-specific prognostic frameworks.

5. **Does a panel-negative result produce an exceptional patient-level prognostic conclusion that should itself be reported?**
- Use panel-negative findings internally when necessary to resolve prognostic criteria or modifiers.
- Do not enumerate panel-negative genes.
- Do not report their absence merely to justify a prognostic category or molecular subgroup.
- If no negative result independently warrants report prose under the workflow reporting policy, classify this rule as OMIT.

6. **What prognostic interpretation follows from the established TP53 allelic state?**
- Apply this rule only when a TP53 mutation has been detected and allelic-state interpretation is therefore relevant.
- If no TP53 mutation is detected, classify this rule as OMIT; do not state that TP53 allelic state or multi-hit status cannot be determined.
- When applicable, state the disease-specific prognostic significance of TP53 according to whether the established state is monoallelic or multi-hit.

# R3 — Clinical actionability

1. **Which detected molecular alteration supports a specific therapy, in what disease and treatment setting, and how established is that implication?**
- Identify the actionable alteration, relevant treatment setting, and whether the implication is established, optional, or investigational.
- Include any necessary approval, treatment-line, trial, or jurisdictional qualification.

2. **Does treatment implication depend on the specific variant (or class of variant)?**
- Base treatment interpretation on the detected variant class rather than other alterations in the same gene.

3. **Which detected molecular alterations modify response, resistance, relapse after therapy, or treatment-specific survival?**
- Consider only the treatment options available to the case given the known demographic, clinical, morphological and molecular results.
- State treatment-specific molecular effects and match the strength of the claim to the evidence.
- Do not convert treatment-specific effects into general prognostic claims.

4. **Do cytogenetic or FISH-defined alterations provide an actionable treatment implication that should be integrated with the molecular findings?**
- State treatment implications of relevant fusions, rearrangements, or deletions detected outside the NGS assay.

5. **Does any detected molecular alteration materially affect transplant-related management?**
- State the specific transplant implication only when supported by evidence
- Do not infer a transplant indication from mutation status alone.
- If the answer to this question is in the negative, classify the answer as `OMIT`.

# R4 — MRD interpretation

1. **Which detected molecular alteration is a validated marker suitable for molecular MRD monitoring for this disease, and how should it be monitored?**
- Identify exactly the preferred marker and appropriate high-sensitivity assay
- Apply disease-specific MRD guidance where available
- Do not transfer AML-specific molecular MRD approaches to other myeloid neoplasms without supporting validation.

2. **When multiple detected alterations are relevant to MRD, which should be preferred for monitoring and which should be complementary?**
- Prioritise the most disease-specific and validated MRD marker.
- Use additional alterations as complementary markers only when supported by validated evidence
- Do not let a less specific marker supersede a more informative one.

3. **If a residual molecular alteration is detected, what does it mean at this specimen and treatment timepoint?**
- Interpret it according to assay sensitivity, quantitative level and serial kinetics.
- Do not infer relapse or treatment failure from an isolated low-level result without appropriate corroboration.

4. **If a previously detected alteration is not detected on follow-up testing, what molecular response can be concluded?**
- Interpret “not detected” within the sensitivity and scope of the assay
- Do not equate routine-panel negativity with biological absence or molecular remission.

# R5 — Possible germline predisposition
- NB: If no germline concern is supported, classify the answer to each of these questions as `OMIT`.

1. **Are any of the detected molecular alterations fall within genes known to be germline predisposition to malignancies?**
- Consider the strength of the evidence as well as the known prevalence of pathogenic germline variants within each gene

2. **Does the VAF of the variant support the possibility of germline origin of the variant?**
- Tumour-only sequencing may discover variants with VAFs that overlap those of germline origin
- Do not confirm germline status from tumour-only sequencing.
- Include appropriate advice to confirm germline status through appropriate testing

3. **Is there any family history, clinical, morphological or other features present that suggest a syndrome associated with germline predisposition to malignancy?**
- Identify every syndromic feature that could possibly support the germline status of the detected variant

4. **Is there any feature that would exclude the germline status of the detected variants?**
- A classic example is TP53 variant in a elderly patient with no family or personal history of cancers; this would effectively rule out Li-Fraumeni syndrome
- Other examples include new diagnosis of a haematological malignancy where a germline syndrome would have expected the malignancy at a much younger age

5. **What molecular architecture supports or weakens the suspicion of germline predisposition?**
- Describe relevant patterns such as a plausible constitutional variant with an acquired second event, while avoiding conclusions not established by the data.

6. **What phase, constitutional-allele or clonal relationships can be established from the available data?**
- State only relationships supported by phasing or lineage-resolved evidence; do not infer cis/trans phase, constitutional allele identity or clonal co-occurrence from bulk VAF alone.

7. **Does uncertainty about germline versus somatic origin alter the interpretation of any prognostic framework?**
- State any patient-specific prognostic implication as provisional pending constitutional testing when germline status changes framework applicability.

# Style requirements

- Lead with the clinically important conclusion.
- Be concise and specific.
- Explain only the molecular facts that change diagnosis, prognosis, management, MRD interpretation or germline assessment.
- Distinguish established findings from possibilities and uncertainties.
- Do not speculate beyond the supplied data.
- Do not fabricate literature, evidence, thresholds, assay performance or treatment approvals.
