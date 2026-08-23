{{ include "includes/ptbg_common.md" }}
{{ include "includes/germline_semantics.md" }}

# Terraced-v5 germline proforma

Discuss EVERY supplied variant ID.

First classify whether each variant is suspicious for possible germline origin using:
- whether the gene has an established germline-predisposition relationship relevant to the current haematological phenotype; and
- whether the observed VAF is compatible with germline origin.

Then, for every `suspect` or `uncertain` variant, assess whether the supplied clinical stem supports a compatible germline syndrome. Absence of supplied family-history/phenotype information is `unknown`, not negative evidence. Do not create `clinical_support` entries for `not_suspect` variants.

Do NOT recommend germline testing, referral or counselling.

Return YAML only:
```yaml
suspect:
  - variants: [v01]
    reason: "established germline predisposition relationship plus VAF-compatible reasoning"
uncertain: []
not_suspect:
  - v02
# `not_suspect` contains bare variant IDs only.
clinical_support:
  - variants: [v01]
    support: "present | absent | unknown"
    reason: "what the clinical stem does or does not show"
```
