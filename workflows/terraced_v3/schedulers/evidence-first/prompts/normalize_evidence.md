# Terraced-v3 evidence normalisation — {{domain}}

Do not make a patient-level clinical decision. From the supplied raw cards, retain only evidence that may materially inform this {{domain}} task and rewrite each retained card as one concise clinically usable claim. Preserve qualifiers and disease scope. Do not combine cards. Do not add outside knowledge.

Return YAML only:
```yaml
evidence_items:
  - card_tag: "[card:0123456789ab]"
    diagnosis_ids: [DX1]
    normalized_claim: "..."
```
For germline evidence, diagnosis_ids should normally be []. Use [] when no supplied card is relevant.

# Settled diagnoses
```yaml
{{diagnoses}}
```

# Raw evidence
{{evidence}}
