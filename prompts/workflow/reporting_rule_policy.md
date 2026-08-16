# Reporting-rule analysis policy

This file is the single source of truth for the patient-level answer style and `REPORT:` versus `OMIT:` classification used by reporting-rule analysis.

## Patient-level conclusion and qualifier style

- State the strongest patient-level conclusion supported by the known facts.
- Use a qualifier only for a material condition that is unresolved in the patient. If the condition is already known, resolve it and state the resulting conclusion directly.
- If a material condition is unresolved, state the best-supported conclusion followed by the specific qualifier, e.g. **“X supports Y, provided that Z.”**
- Do not withhold a supported conclusion just because some information is missing.
- Do not speculate about possibilities that the known patient facts have already ruled out.

## REPORT versus OMIT classification

Classify the **patient-level outcome of the rule**, not the importance of the question and not the existence of a potentially relevant evidence card.

### REPORT

Use `REPORT:` only when the rule produces patient-specific content that belongs in the final clinical report. This includes:

- a detected variant that changes or materially refines diagnosis, prognosis or treatment;
- a detected variant that is a clinically relevant biomarker;
- a detected finding that raises possible germline predisposition;
- an absent finding that materially contradicts or excludes the supplied provisional diagnosis;
- an expected finding whose presence or absence materially changes diagnosis, prognosis or treatment;
- a detected clone supporting clonal haematopoiesis when no haematological neoplasm is otherwise established;
- a detected finding supporting dual pathology;
- an established favourable, adverse, neutral or other disease-specific prognostic contribution of a detected pathogenic or likely pathogenic variant;
- a relevant applicable prognostic framework or score when the rule requires it;
- a specific variant-level limitation or caution that is itself clinically useful and the canonical rule explicitly calls for it, such as a detected alteration that should not be used as a stand-alone MRD marker.

A reportable negative finding must lead with its **clinical effect**, not with a generic absence statement. For example, write `The absence of <finding> argues against <diagnosis>.` rather than `No <finding> was detected.`

### OMIT

Use `OMIT:` when the rule has been evaluated but produces no patient-specific content that should appear in the final report. In particular:

- if the answer's clinical conclusion would begin `No ...` or `Not applicable ...`, classify the rule `OMIT:` rather than converting that non-finding into report prose;
- if a rule is conditional and its premise is not met, classify it `OMIT:`; do not answer the consequent with generic recommendations merely because an evidence card discusses them;
- omit absence of a variant that is not specifically expected or clinically material in the supplied context;
- omit statements that treatment does not change from standard practice because no actionable alteration was detected;
- omit generic statements that none of the detected variants are suitable molecular MRD markers;
- omit generic statements that none of the detected variants raise germline concern;
- omit generic statements that there is no relevant prognostic evidence, no actionable alteration, no relevant kinase alteration, no treatment-specific effect, no transplant implication, no validated MRD marker, no applicable follow-up result, no informative germline architecture, or no other rule-specific finding;
- omit a rule whose requested finding, event, follow-up specimen, molecular class, allelic state, or other prerequisite is absent and where no separate clinically useful interpretation follows.

`R0.1` is the explicit exception: it is always `REPORT:` even when the required result sentence is `No pathogenic variants were detected on NGS.`

Do not use `OMIT:` merely because a conclusion is negative in wording. A **specific detected finding with a clinically useful negative/cautionary interpretation** may still be `REPORT:` when that interpretation changes how the detected finding should be understood or used. Conversely, the presence of a citation does not make a non-applicable rule reportable.

When a canonical reporting rule explicitly requires `OMIT:` in a stated circumstance, that instruction is binding.
