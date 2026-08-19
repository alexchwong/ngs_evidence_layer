# Terraced-v1 negative-reportability filter

Classify every accepted clinical fact for reportability before final report synthesis.

Return exactly one classification row for every supplied `fact_id`, including facts that are clearly reportable. Preserve the supplied fact order and return only:

```yaml
classifications:
  - fact_id: diagnosis-1
    class: positive_conclusion
  - fact_id: mrd-2
    class: routine_negative
  - fact_id: germline-1
    class: routine_negative
  - fact_id: diagnosis-3
    class: exceptional_negative
```

Use exactly one of these closed class values:

- `positive_conclusion` — a positive patient-level conclusion, including one derived from negative premises;
- `routine_negative` — quarantine material under the routine-negative policy below; or
- `exceptional_negative` — a negative that independently qualifies under the exceptional-negative rule below and must remain eligible for reporting.

It is valid for no fact to be classified `routine_negative`, but the `classifications` list itself must still contain every supplied fact exactly once.

Examples: an MRD fact saying that DNMT3A is unsuitable or not reportable as a marker is `routine_negative` when appropriate positive NPM1 or FLT3 marker guidance can be reported and the caution does not independently change management. A fact saying that no germline concern or no germline-predisposition fact is reportable is `routine_negative`; this includes a no-concern paragraph reframed as reassurance that findings are consistent with somatic origin. A dedicated negative result that independently resolves a supplied patient-specific diagnosis, requested test, or management decision may instead be `exceptional_negative`.

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
- standard practice is unchanged because no actionable alteration was detected;
- no current MRD status can be assigned solely because the specimen is diagnostic and no dedicated post-treatment MRD result was supplied;
- a detected alteration is unsuitable for MRD when an appropriate positive marker can instead be reported and the caution does not independently change patient management.

Apply this by meaning, not wording. Rephrasing `No X` as `X is not present`, `X does not apply`, `X does not alter Y`, or similar does not make it reportable.

Do not quarantine a positive patient-specific conclusion merely because routine negative findings were used internally to derive it. Report the resulting positive diagnosis, classification, prognostic category, or treatment conclusion rather than its routine negative premises.

For a diagnostic specimen, retain a positive fact that explicitly identifies a validated or preferred prospective MRD marker and any supported recommendation to establish its baseline with the intended sensitive assay. This is positive patient-specific monitoring guidance, not a missing follow-up result. If positive guidance and a routine negative are improperly combined in one fact, classify the fact by whether its primary patient-level conclusion is the prospective marker or baseline recommendation; the semantic reviewer should normally have required those ideas to be separated before this stage.

## Exceptional negative: retain

Do not quarantine an absent finding when the absence itself is an exceptional patient-level result that should independently appear in the clinical report, especially when it materially contradicts or excludes a supplied patient-specific diagnosis or hypothesis.

Also retain a clinically useful negative or cautionary interpretation of a specific detected finding only when that caution independently changes how the finding should be understood or used in patient management. Do not retain an unsuitable-MRD-marker list merely for completeness when the report can state the appropriate positive marker.

## Strict operation boundary

- Classify every supplied `fact_id` exactly once; do not omit facts you consider reportable.
- Use only supplied `fact_id` values and the three allowed class values.
- Do not rewrite, merge, add, or delete facts yourself.
- Use `reason` only as context for classifying the associated fact.
- Do not make citation decisions and do not search for new evidence.
