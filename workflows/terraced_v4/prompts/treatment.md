# Terraced-v4 treatment proforma

Discuss EVERY supplied variant ID. A variant may have multiple distinct treatment effects. A variant with no supported treatment implication must appear in `no_effect`.

Return YAML only:
```yaml
drug_target:
  - variants: [v01]
    therapy: "drug or drug class"
    reason: "why this variant is a treatment target"
drug_resistance:
  - variants: [v02]
    therapy: "drug or drug class"
    reason: "why this variant predicts or confers resistance"
other: []
no_effect:
  - v03
  - v04
# `no_effect` contains bare variant IDs only. Do not put `variants`, `therapy`,
# or `reason` mappings under `no_effect`.
```
