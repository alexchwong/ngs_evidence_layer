{{ include "includes/ptbg_common.md" }}
{{ include "includes/prognosis_semantics.md" }}

# Terraced-v5 prognosis proforma

Discuss EVERY supplied variant ID. A variant may have multiple prognostic entries. A variant with no supported prognostic effect must appear in `no_effect`.

Return YAML only:
```yaml
favorable: []
adverse:
  - variants: [v01]
    reason: "one discrete prognostic proposition"
other: []
uncertain: []
no_effect:
  - v02
# `no_effect` contains bare variant IDs only: no variants/reason/source mapping.
overall: null
# OR, only when this workflow can actually assign an overall molecularly supported framework classification:
# overall:
#   classification: "named framework/tier"
#   reason: "why this overall classification applies"
```
