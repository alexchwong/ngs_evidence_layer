# Diagnosis-lab report fact grounding

For every supplied immutable report fact, write one concise supporting reason and map that reason to the supplied initial-case and reviewed-diagnostic-state source IDs.

Return YAML only with exactly this structure:

```yaml
facts:
  - fact_id: diagnosis-summary-1
    fact: "<copied exactly from the supplied immutable fact>"
    reason: "<why the supplied case and reviewed diagnostic state warrant this report proposition>"
    source_case_fact_ids: [F1]
    source_diagnostic_ids: [D1-WHO5, DX-FINAL-F1]
```

Rules:
- Include every supplied fact exactly once and preserve the supplied order.
- Copy every `fact_id` and `fact` character-for-character.
- Do not add, delete, merge, split, soften, strengthen, or otherwise revise a report fact.
- Use only source IDs explicitly supplied in the input.
- Every row must cite at least one case or diagnostic source ID.
- A reason must explain why the report fact follows from the supplied sources; it must not introduce a new report proposition, diagnosis, criterion, threshold, exclusion, test result, recommendation, or numerical comparison.
- Patient-specific observations should normally map to case fact IDs and may also map to diagnostic supporting-fact IDs.
- Classifier labels and dispositions should map to the applicable diagnosis outcome IDs.
- Qualification or retained-routing propositions may map to uncertainty IDs, diagnosis outcome IDs, and the supplied routing-state ID.
- Do not infer that missing information is a negative finding.
- Do not resolve a supplied uncertainty by assumption.
- Do not use or request evidence cards in this pass.
- Do not write citations, runtime card tags, prose outside the YAML object, or chain-of-thought.