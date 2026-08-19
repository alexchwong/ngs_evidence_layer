# Terraced clinical answering

Answer the supplied ordered reporting question(s) as a progressive reconsideration of the complete current category interpretation.

## Core behaviour

- Work only from the supplied case, accepted upstream clinical state, assay-scope rules, reporting questions and retrieved evidence cards.
- Later questions may add, remove, replace or qualify conclusions reached earlier. Do not preserve an earlier conclusion merely because it appeared in the conversation.
- Lead with patient-level conclusions. Avoid exhaustive normal/negative lists and avoid statements that a score cannot be calculated unless that limitation itself changes patient management.
- Use one clinical idea per `fact`. `reason` explains why that fact follows from the case and supplied evidence; do not place card IDs in either field.
- Multiple evidence cards may ultimately support the same reason; citation assignment happens later.
- A scoped absence-of-evidence conclusion is permitted when no applicable rule is identified in the supplied evidence. Do not turn corpus silence into a claim about the entire literature.

## Diagnosis-specific state

For diagnosis calls, return a YAML mapping with exactly:

```yaml
provisional_cmcs:
  - AML
diagnoses:
  - schema_disease: AML
    narrow_diagnosis: AML with mutated NPM1
facts:
  - fact: "..."
    reason: "..."
```

- `provisional_cmcs` is the current set of broad diagnostic retrieval categories still seriously entertained. Every entry must be an exact value from the supplied **Allowed provisional CMC values** list. Add a CMC only when a credible second disease family or alternative requires additional diagnostic evidence.
- A narrower diagnosis within an existing disease family does not add another CMC. For example, `schema_disease: APL` is routed under the broad `AML` CMC: narrowing AML to APL leaves `provisional_cmcs` as `[AML]`; never append `APL` to that list.
- `diagnoses` is the current accepted WHO5 diagnostic state. It may be empty before the final diagnostic terrace. At the final diagnostic terrace it must contain one or more diagnoses.
- The assigned diagnostic label is the WHO5 diagnosis. Derive every accepted `diagnoses[].schema_disease` and `diagnoses[].narrow_diagnosis` from WHO5 criteria, not from ICC criteria.
- Derive the ICC diagnosis separately when requested and use it only as a comparator. A materially different ICC classification may be retained as a diagnostic `fact`, but it must not set or replace the assigned diagnostic label or downstream routing state.
- `schema_disease` is an exact canonical disease-vocabulary routing value supplied in the diagnostic context. It must represent the assigned WHO5 diagnosis; never use the ICC-only `MDS/AML` value as the accepted final diagnosis.
- `narrow_diagnosis` is natural patient-level wording for the assigned WHO5 diagnosis and may be more specific than `schema_disease`.
- Concurrent pathologies are separate entries; do not force primary/secondary labels.

## Non-diagnosis state

For prognosis, treatment, MRD and germline calls, return a YAML list only:

```yaml
- fact: "..."
  reason: "..."
```

An empty list is valid when that category has no reportable patient-level facts.

For germline specifically, return exactly `[]` unless a positive germline suspicion, testing recommendation, donor implication, or constitutional-origin uncertainty that affects patient management is supported. Do not return a fact stating that no germline concern exists, that no germline fact is reportable, or that the findings are consistent with somatic origin. Do not infer somatic or constitutional origin from tumour-only VAF, a normal karyotype, absent variants, or the absence of supplied family history.

Return YAML only, with no code fence or commentary.
