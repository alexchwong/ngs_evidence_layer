# Clinical assertion policy

## Clinical reporting eligibility

A clinically relevant source assertion is one that could materially contribute to a concise myeloid NGS report by informing:

- diagnosis or classification;
- patient-level prognosis;
- treatment selection, eligibility, sensitivity, resistance, or management;
- MRD interpretation; or
- assessment of possible germline predisposition or germline evaluation.

The assertion must apply to the stated disease, molecular finding, and clinical context. A clinical endpoint is **not** by itself a clinical interpretation: survival, response, relapse, or another important endpoint qualifies only when the source establishes a clinically meaningful implication of the molecular finding.

Background information is not clinically useful by itself, including prevalence, epidemiology, study methodology, molecular mechanism alone, descriptive co-occurrence, or a descriptive association without a patient-level clinical implication. A negative or null result is useful only when the source supports a clinically meaningful negative conclusion whose absence would materially change interpretation or management; statistical non-significance alone does not establish no effect.

When several measurements, effect estimates, or component observations support the same clinical conclusion, treat the clinical conclusion as the assertion rather than treating each supporting statistic as a separate assertion. A number warrants its own assertion only when the value itself is clinically operative for applying a source-supported rule to an individual patient.

Geneless diagnosis and treatment eligibility is governed by the separately injected `GENELESS_CLAIM_POLICY`.

## Category semantics

Assign category according to the clinical role actually established by the source assertion, not according to the paper section, keywords, gene, or intended downstream use.

- `diagnosis`: the source states a molecular, morphologic, clinical, quantitative, or other criterion that defines, supports, excludes, differentiates, or changes a diagnosis or classification.
- `prognosis`: the source explicitly establishes an outcome, risk, survival, progression, relapse, or patient-level effect within a named prognostic framework. A recognised prognostic framework may itself be clinically relevant, but model coefficients, score weights, point assignments, model-construction variables, calibration/discrimination statistics, and score-category survival tables do not qualify by themselves.
- `treatment`: the source explicitly supports treatment selection, eligibility, standard treatment, sensitivity, resistance, response, or another treatment-specific clinical effect.
- `biomarker`: the source explicitly assigns a testing, detection, monitoring, or discrimination role that remains independently useful rather than merely relabelling the same diagnostic assertion. State that independent biomarker function.
- `germline`: the source explicitly concerns inherited, constitutional, or predisposition status, or germline evaluation. Preserve the source's degree of certainty; an indication or recommendation for germline evaluation does not establish constitutional status.

Do not change category merely to satisfy a schema constraint or make an otherwise ineligible assertion ingestible. When one passage supports multiple independently useful clinical roles, treat those roles as separate assertions rather than combining their categories into one ingestion unit. The same evidence may legitimately support distinct roles when each role has independent clinical meaning.

## Atomicity and qualifiers

One census assertion or evidence card represents **one independently retainable/rejectable clinical proposition**. If one material clinical proposition could be retained or rejected independently of another, they are separate assertions.

A qualifier is information necessary to define, narrow, condition, or state an exception to that **same proposition**. Qualifiers may include disease, population, molecular context, treatment/comparator, threshold, subgroup or analysis context when it materially limits applicability, exception, uncertainty, and other meaning-critical applicability conditions.

Disease, population, molecular context, treatment, comparator, threshold, analysis, exception, uncertainty, and other qualifiers required to preserve meaning or applicability belong with the assertion and must not be split from it.

A related statement is **not** a qualifier merely because it provides context. If additional text introduces a second conclusion about another subject, framework, treatment setting, outcome, recommendation, limitation, or applicability question that can stand independently, it is a separate assertion.

Apply the **deletion / independent-retention test**: remove the suspected qualifier. If the remaining text is still a complete clinical proposition and the removed text could itself be retained or rejected without changing the truth or applicability of that proposition, the removed text is a separate assertion and must not ride along as a qualifier.

Do not split away a true qualifier required to preserve the exact meaning or applicability of its proposition. Do not merge assertions merely because they share a gene, disease, category, paragraph, sentence, table, study population, clinical framework, or underlying evidence.

Statistics or component observations that quantify or support one clinical conclusion are not separate ingestion units. Hazard ratios, odds ratios, confidence intervals, P values, cohort sizes, median survival values, response percentages, model coefficients, score weights, and similar study-result packaging remain supporting evidence unless the number itself is clinically operative.

A single atomic assertion may require more than one source sentence or fragment for complete support. Conversely, one source sentence or census entry may contain multiple atomic assertions and must then be split. Prefer the smallest unit that preserves one complete, independently useful clinical meaning.
