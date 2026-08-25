# Diagnosis-lab report synthesis

Write a concise patient-level diagnostic interpretation that answers this reporting question:

> What diagnostic interpretation should be reported from the supplied case and reviewed diagnostic state, including the diagnosis or diagnostic possibility supported by the findings, the material limitations preventing firmer classification, and the current diagnostic designation that should be retained?

This is a representation pass over the supplied initial case and reviewed diagnostic state. Do not perform new diagnostic reasoning, search for evidence, or force a definitive diagnosis when the supplied state does not support one.

Use:
- the initial case notes and structured case as authoritative for patient-specific observations;
- the reviewed diagnostic state for classifier-specific diagnostic interpretation, retained routing, supporting propositions, and material uncertainties.

Requirements:
- State what diagnosis is assigned or what diagnosis is raised as a candidate.
- Do not print machine-state terms or field names such as `established`, `indeterminate`, `not_established`, `not_applicable`, `schema_disease`, or `provisional_cmcs`.
- When a diagnosis is not established, use natural clinical wording such as "raises", "supports consideration of", "is consistent with", or "cannot yet be assigned".
- Do not imply that a candidate label is an assigned diagnosis.
- Explain only material limitations represented in the supplied uncertainties and consistent with the initial case.
- If an uncertainty contradicts an explicit patient observation in the initial case, preserve the explicit case observation and do not repeat the contradiction.
- Integrate overlapping uncertainties by their diagnostic consequence rather than producing a checklist of absent findings.
- Do not turn missing information into a negative biological finding, negative assay result, or excluded diagnosis.
- Do not write exhaustive statements of what was not detected, assessed, or excluded.
- Do not introduce a criterion, threshold, test result, diagnosis, exclusion, recommendation, or numerical value absent from the supplied inputs.
- Do not include statements that merely clarify what the diagnosis is not or what does not preclude it. Only include limitations that materially affect diagnostic confidence or clinical management.
- Do not write negative propositions such as "X does not preclude Y" or "X cannot be excluded" unless the uncertainty would change clinical management.
- Do not include uncertainties about data that was not collected or reported in the case.
- Do not include statements that query whether reported findings meet specific thresholds.
- Preserve paired WHO5 and ICC wording compactly. Discuss a classifier difference only when the reviewed state marks it as materially different.
- State the retained broad diagnostic designation when a candidate diagnosis does not control current routing.
- Preserve genuine concurrent pathologies as separate propositions when supplied.
- One report proposition per sentence.
- Write exactly one sentence per physical line.
- End every sentence with a full stop.
- Return prose only under the exact standalone heading `**Diagnosis**`.
- Do not write citations, card tags, YAML, bullets, a bibliography, or commentary outside the report.
