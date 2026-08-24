# Prognosis

Using only the supplied case, diagnosis, and prognosis cards, classify every supplied variant once by its principal supported prognostic effect in the current disease context.

Rules:
- Variants sharing the same clinical proposition, framework, polarity, context, and qualifiers MUST be in one row.
- `reason` is one concise report-ready clinical proposition shared by all variants in that row.
- Preserve qualitative strength from the evidence; do not weaken or strengthen it.
- Do not infer that one variant cancels another unless the supplied evidence explicitly defines that interaction.
- `prognostic_score` is populated only when this workflow can actually assign the named score/risk group from supplied information. Otherwise use null. Never say a score is "not calculable".

Return YAML only:
```yaml
favorable: []
adverse: []
neutral: []
uncertain: []
prognostic_score: null
```

Effect rows use:
```yaml
- variants: [v01, v02]
  reason: "<one shared prognostic proposition>"
```

A populated score uses:
```yaml
prognostic_score:
  name: "<framework>"
  result: "<risk group/score>"
  reason: "<one concise basis>"
```
