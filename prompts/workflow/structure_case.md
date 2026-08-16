# Structure the clinical case

## Task

Transform `case.md` into the structured case representation required by the workflow, using only the supplied case and the allowed case-major-category list.

Apply the shared patient-result semantics in the active workflow specification (`workflows/legacy/SKILL.md` or `workflows/prototype/SKILL.md`, as selected by the entry point) when interpreting missing, complete, negative, or assumed results.

## Task-specific rules

### `case_major_category`

- Choose exactly one value from `case-major-categories.json`.
- Represent the supplied starting **clinicomorphological major category**, not a molecularly revised diagnosis.
- Use `no_haematological_malignancy` only when the case specifies no haematological malignancy and the NGS result block contains no variants.
- Do not use `no_haematological_malignancy` if variants are present.

### `provisional_disease`

- Preserve the supplied provisional diagnostic wording, including any subtype/entity wording such as `MDS-IB2`.
- Do not force it to a controlled-vocabulary term.
- Do not revise it using molecular findings.

### `genes`

- Include only genes with reported variants in the NGS result block.
- Exclude genes mentioned only in history, differential diagnosis, assay description, other tests, or lists of genes tested.
- Use `[]` when no NGS variants are reported.

### `case_facts`

- Preserve supplied patient facts losslessly with unique, stable `fact_id` values.
- Preserve exact variants, values, units, morphology, blood counts, cytogenetic/FISH findings, treatment context, assay limitations, and qualifiers.
- Do not strengthen or normalise supplied facts.
- Do not infer phase, clonal order, allelic state, germline origin, assay coverage, or unreported clinical features.
- Record one `test_result_status` fact for each supplied test treated as complete.
- Do not create separate negative facts for every unlisted gene or abnormality.
- Record an assumed normal cytogenetic result as a `workflow_assumption`, not a patient result.

## Output contract

Return JSON only with exactly these top-level fields:

```json
{
  "case_major_category": "<exact allowed major category>",
  "provisional_disease": "<supplied provisional diagnostic wording>",
  "genes": [],
  "case_facts": []
}
```

Do not add explanatory prose or other top-level fields.

## Final check

Before returning, verify privately that `case_major_category` is an exact allowed value, `provisional_disease` preserves the supplied wording, `genes` contains only genes with reported NGS variants, and every structured fact is grounded in `case.md` or is explicitly labelled as a workflow assumption permitted by the active workflow specification.
