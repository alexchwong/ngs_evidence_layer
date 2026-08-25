{{ include "includes/ptbg_common.md" }}
{{ include "includes/biomarker_semantics.md" }}

# Terraced-v5 biomarker/MRD proforma

Discuss EVERY supplied variant ID. Decide whether each finding is suitable, unsuitable, uncertain, or has no meaningful MRD implication in the current disease context.

Return YAML only:
```yaml
suitable_mrd:
  - variants: [v01]
    reason: "why suitable for MRD"
unsuitable_mrd:
  - variants: [v02]
    reason: "why unsuitable for MRD"
uncertain: []
no_effect:
  - v03
# `no_effect` contains bare variant IDs only: no reason/effect mapping.
```
