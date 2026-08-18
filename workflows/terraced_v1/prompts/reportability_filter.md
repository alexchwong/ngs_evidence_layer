# Terraced-v1 negative-reportability filter

Identify accepted clinical facts that are routine negative, absent, non-applicable, or no-finding statements that should be quarantined before final report synthesis.

Return only:

```yaml
quarantine_fact_ids:
  - prognosis-2
  - treatment-3
```

An empty list is valid.

Classify the patient-level fact, not the importance of the question and not whether evidence exists for it.

## Quarantine routine negatives

The absence of an abnormality is normally the default state and should remain silent. Quarantine facts whose patient-level meaning is any of the following unless the negative itself independently qualifies under the exceptional-negative rule below:

- no finding was detected;
- a finding, subgroup, modifier, diagnosis, treatment implication, or framework does not apply;
- a wild-type, exclusion, or other negative criterion was satisfied only as a premise for a positive conclusion;
- an evidence-defined subgroup or stronger association does not apply because a premise is unmet;
- a prognostic score cannot be calculated because non-molecular variables are unavailable;
- no relevant prognostic evidence, actionable alteration, kinase alteration, treatment-specific effect, transplant implication, validated MRD marker, follow-up result, germline concern, or other rule-specific finding exists;
- none of the detected variants has a clinically useful contribution for the category;
- standard practice is unchanged because no actionable alteration was detected.

Apply this by meaning, not wording. Rephrasing `No X` as `X is not present`, `X does not apply`, `X does not alter Y`, or similar does not make it reportable.

Do not quarantine a positive patient-specific conclusion merely because routine negative findings were used internally to derive it. Report the resulting positive diagnosis, classification, prognostic category, or treatment conclusion rather than its routine negative premises.

## Exceptional negative: retain

Do not quarantine an absent finding when the absence itself is an exceptional patient-level result that should independently appear in the clinical report, especially when it materially contradicts or excludes a supplied patient-specific diagnosis or hypothesis.

Also retain a clinically useful negative or cautionary interpretation of a specific detected finding when it changes how that detected finding should be understood or used.

## Strict operation boundary

- Select only supplied `fact_id` values.
- Do not rewrite, merge, add, or delete facts yourself.
- Use `reason` only as context for classifying the associated fact.
- Do not make citation decisions and do not search for new evidence.
