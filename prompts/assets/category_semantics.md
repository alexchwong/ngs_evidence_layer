# Category semantics

Assign category according to the clinical role actually established by the source assertion, not according to the paper section, keywords, gene, or intended downstream use.

- `diagnosis`: the source states a molecular, morphologic, clinical, quantitative, or other criterion that defines, supports, excludes, differentiates, or changes a diagnosis or classification.
- `prognosis`: the source explicitly establishes an outcome, risk, survival, progression, relapse, or named prognostic-model effect.
- `treatment`: the source explicitly supports treatment selection, eligibility, standard treatment, sensitivity, resistance, response, or another treatment-specific clinical effect.
- `biomarker`: the source explicitly assigns a testing, detection, monitoring, or discrimination role that remains independently useful rather than merely relabelling the same diagnostic assertion. State that independent biomarker function.
- `germline`: the source explicitly concerns inherited, constitutional, or predisposition status, or germline evaluation. Preserve the source's degree of certainty; an indication or recommendation for germline evaluation does not establish constitutional status.

Do not change category merely to satisfy a schema constraint or make an otherwise ineligible assertion ingestible.

When one passage supports multiple independently useful clinical roles, treat those roles as separate assertions rather than combining their categories into one ingestion unit. The same evidence may legitimately support distinct roles when each role has independent clinical meaning.
