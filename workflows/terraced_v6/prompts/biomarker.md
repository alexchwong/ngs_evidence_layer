# MRD markers

Using only the supplied case, diagnosis, and MRD/biomarker cards, classify every supplied variant as either an MRD marker or not an MRD marker in the current disease context.

Rules:
- Variants sharing the same proposition, framework, context, and qualifiers MUST be in one row.
- `reason` is one concise evidence-backed proposition.
- Do not recommend a marker unless the supplied evidence supports its use for MRD in the current context.

Return YAML only:
```yaml
mrd_marker: []
not_mrd_marker: []
```

Rows use:
```yaml
- variants: [v01]
  reason: "<one shared MRD proposition>"
```
