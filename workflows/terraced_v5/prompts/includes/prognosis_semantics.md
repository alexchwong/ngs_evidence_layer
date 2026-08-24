# Prognosis interpretation boundaries

Assess two distinct questions:

1. What prognostic association, if any, does each variant have in the current disease context?
2. What is the patient's overall classification under an applicable named prognostic framework?

Do not infer one directly from the other.

- A variant may have an adverse or favorable prognostic association while the patient's overall framework classification is different.
- Being disease-defining, classification-defining, or diagnostically important does not by itself make a variant prognostically favorable or adverse.
- If an association is supported only in a particular treatment setting or population, preserve that context in the reason. Do not generalize it to all patients with the disease.
- For `overall`, populate a named framework/tier only when this workflow is intended to assign that overall classification from the available molecular/diagnostic inputs. Do not derive the overall tier by simply combining per-variant favorable/adverse labels.
- Do not offer to calculate composite prognostic scores that require non-molecular score parameters. For those frameworks set `overall: null`; do not state that the score is not calculable, unavailable, incomplete, or missing variables. Authority-backed molecular effects from such frameworks may still be reported in the variant-effect buckets.
- Do not cancel or reverse one variant's supported prognostic association merely because another variant has a different association, unless supplied evidence explicitly defines that modifying relationship.
- Use `uncertain` when prognostic evidence is conflicting, context-dependent, or insufficient to assign direction.
- Use `no_effect` when no clinically reportable prognostic contribution is supported for that variant.
