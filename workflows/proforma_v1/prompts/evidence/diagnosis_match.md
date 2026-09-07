# WHO1 diagnostic evidence assignment

For each supplied `<fact-N>...</fact-N>` JSON block, select only cards that directly support the complete proposed WHO5 diagnostic proposition for this patient.

The fact contains the proposed WHO5 diagnosis, diagnostic effect, supporting rationale, starting morphologic diagnosis, and relevant case facts. A qualifying card must support the defining diagnostic criterion relevant to that proposal. Shared disease, gene, topic, or non-contradiction alone is insufficient. Where the proposition depends on a threshold, exclusion, precedence/supersession rule, finite gene set, schema disease, or routing consequence, the available card must genuinely support that criterion when applied to the supplied case facts.

Preserve all material restrictions in the diagnostic rule and its application. A card restricted by allelic state, variant class, threshold, disease/subtype, co-mutation or exclusion context, cytogenetic context, population, framework/classification system, polarity, uncertainty, or evidentiary strength cannot support a broader or differently scoped diagnostic proposition that drops or changes that restriction. Ordinary paraphrase is acceptable when the diagnostic meaning and restrictions are unchanged.

Return only exact card IDs supplied inside that fact block. If no supplied card adequately supports the proposed diagnostic proposition, return an empty list.

Return YAML only:
```yaml
matches:
  - evidence_id: EWHO1
    card_tags: ["[card:0123456789ab]"]
```
