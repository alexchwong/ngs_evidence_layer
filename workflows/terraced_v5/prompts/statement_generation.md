# Atomic reportable statement generation

For EVERY supplied proforma element, generate exactly one concise, self-contained clinical statement representing that element.

Use only the supplied proposition and reasons. Preserve disease/variant scope, polarity, uncertainty, named framework, treatment context, thresholds, and conditional qualifiers. Do not add clinical facts or relationships absent from the proforma element.

`variant_display` contains the human-readable variant identities for report prose. Internal variant IDs are provenance metadata and are deliberately not supplied here; never invent or reconstruct internal IDs in the reportable statement.

A condition may qualify an already-supported conclusion when a genuinely pending/unknown discriminator could alter it. Do not use a condition to invent missing positive defining evidence.

Return YAML only, preserving schema IDs and order:
```yaml
statements:
  - schema_id: "PX-ADVERSE-01"
    statement: "One atomic reportable clinical statement."
```
