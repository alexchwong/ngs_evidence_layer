# Terraced-v4 germline proforma

Discuss EVERY supplied variant ID.

First classify whether each variant is suspicious for possible germline origin using only:
- whether the gene is a recognised germline predisposition gene;
- whether the observed VAF is compatible with germline origin.

A variant is `suspect` only when BOTH conditions are met: the gene is a recognised germline-predisposition gene AND the observed VAF is compatible with germline origin. A VAF near 50% by itself is not evidence that a variant is germline.

Use `not_suspect` when the gene is not a recognised germline-predisposition gene, even if the VAF could numerically be compatible with heterozygous germline origin. Do NOT use `uncertain` merely because no germline evidence card was supplied. Use `uncertain` only when there is a genuine unresolved germline-predisposition/VAF classification issue after applying your clinical knowledge and the supplied case.

Then, for every `suspect` or `uncertain` variant, assess whether the supplied clinical stem supports a compatible germline syndrome (for example relevant family history, age, phenotype or syndrome-specific features). Absence of supplied family-history/phenotype information is `unknown`, not negative evidence. Do not create `clinical_support` entries for `not_suspect` variants.

Do NOT recommend germline testing, referral or counselling.

Return YAML only:
```yaml
suspect:
  - variants: [v01]
    reason: "known germline gene and VAF-compatible reasoning"
uncertain: []
not_suspect:
  - v02
# `not_suspect` contains bare variant IDs only.
clinical_support:
  - variants: [v01]
    support: "present | absent | unknown"
    reason: "what the clinical stem does or does not show"
```
