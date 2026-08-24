# Treatment implications

Using only the supplied case, diagnosis, and treatment cards, address every supplied variant.

Buckets:
- `drug_target`: the molecular lesion is directly targetable.
- `drug_sensitive`: the finding predicts increased sensitivity/response without itself being the direct target.
- `drug_resistant`: the finding predicts resistance or reduced response.
- `no_drug_implication`: no supported therapeutic implication in the supplied evidence/context.

Rules:
- A variant may appear in more than one positive bucket when the propositions are genuinely distinct.
- Variants sharing the same proposition, therapy, context, and qualifiers MUST be in one row.
- A variant with any positive treatment implication must not appear in `no_drug_implication`.
- Keep reasons concise and evidence-backed.

Return YAML only:
```yaml
drug_target: []
drug_sensitive: []
drug_resistant: []
no_drug_implication: []
```

Positive rows use:
```yaml
- variants: [v01]
  therapy: "<drug or drug class>"
  reason: "<one shared treatment proposition>"
```

Negative rows use:
```yaml
- variants: [v02]
  reason: "<one shared negative proposition>"
```
