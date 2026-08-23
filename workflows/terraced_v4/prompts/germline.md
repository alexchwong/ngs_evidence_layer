# Terraced-v4 germline proforma

Discuss EVERY supplied variant ID.

First classify whether each variant is suspicious for possible germline origin using only:
- whether the gene is a recognised germline predisposition gene;
- whether the observed VAF is compatible with germline origin.

Then, for every `suspect` or `uncertain` variant, assess whether the supplied clinical stem supports a compatible germline syndrome (for example relevant family history, age, phenotype or syndrome-specific features). Absence of supplied family-history/phenotype information is `unknown`, not negative evidence.

Do NOT recommend germline testing, referral or counselling.

Return YAML only:
```yaml
suspect:
  - variants: [v01]
    reason: "known germline gene and VAF-compatible reasoning"
uncertain: []
not_suspect: []
clinical_support:
  - variants: [v01]
    support: "present | absent | unknown"
    reason: "what the clinical stem does or does not show"
```
