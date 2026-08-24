# Atomic reportable statement generation

For EVERY supplied proforma element, generate exactly one concise, self-contained clinical statement representing that element.

Use only the supplied proposition and reasons. Preserve disease/variant scope, diagnosis label, polarity, uncertainty, named framework, treatment context, thresholds, and conditional qualifiers. Do not add clinical facts, relationships, modifiers, zygosity, molecular qualifiers, exclusions, or diagnostic requirements absent from the proforma element.

If `locked_terms` are supplied, reproduce every locked term exactly in the statement. They are validated provenance anchors and must not be replaced by a synonym, broader/narrower label, or fallback diagnosis.

`variant_display` contains the human-readable variant identities for report prose. Internal variant IDs are provenance metadata and are deliberately not supplied here; never invent or reconstruct internal IDs in the reportable statement.

A condition may qualify an already-supported conclusion only when that conditionality is already present in the supplied proforma element. Do not introduce a new condition or exclusion.

Return YAML only, preserving schema IDs and order:
```yaml
statements:
  - schema_id: "PX-ADVERSE-01"
    statement: "One atomic reportable clinical statement."
```
