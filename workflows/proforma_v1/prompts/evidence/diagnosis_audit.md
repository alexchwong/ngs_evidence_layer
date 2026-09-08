# WHO1 diagnostic evidence audit

Independently audit each supplied WHO1 diagnostic fact/card pair. The fact contains the proposed WHO5 diagnosis, diagnostic effect, supporting rationale, starting morphologic diagnosis, and relevant case facts.

For a primary-diagnosis proposition, the card must genuinely support the relevant defining diagnostic criterion as applied to those facts, not merely be related to the disease or gene.

For a concurrent-pathology proposition, apply compositional support. The supplied case facts may establish that the patient has findings compatible with a separate pathology; the authority card does not need to describe that exact co-occurrence or prove the second diagnosis in this patient. The card is sufficient when it supports the disease-specific molecular premise used to raise the concurrent pathology, such as that the variant is a hallmark, defining molecular subset, diagnostic criterion, useful discriminator/differential marker, or other strong clinically meaningful signal for the named distinct disease, disease family, or lineage. Do not fail such a card merely because it does not state that the pathology can coexist with the primary disease or does not independently establish the second neoplasm.

Assess defining criteria, required thresholds, exclusions, precedence/supersession, finite gene-set membership, schema disease and derived routing consequence where applicable. Preserve all material restrictions in the diagnostic rule and its application, including where relevant allelic state, variant class, threshold, disease/subtype, co-mutation or exclusion context, cytogenetic context, population, framework/classification system, polarity, uncertainty, and evidentiary strength. A narrower or differently scoped card does not support a broader proposition that drops or changes such a restriction. Ordinary paraphrase is acceptable when the diagnostic meaning and restrictions are unchanged.

For a primary-diagnosis proposition, mark `card_is_element_of_reason: true` only when the card supports the complete proposed diagnostic proposition represented by the fact. For a concurrent-pathology proposition, mark it true when the card supports the literature-dependent molecular premise and the remaining patient-specific premise is supplied as case facts.

Return exactly one audit for every supplied card and no others. Preserve the supplied evidence ID, card tag, and order exactly.

Return YAML only in this exact shape:
```yaml
audits:
  - evidence_id: EWHO1
    card_audits:
      - card_tag: "[card:0123456789ab]"
        card_is_element_of_reason: true
        risk: none
        comments: []
```

Use `risk: warning` only for a non-gating fidelity/context concern after sufficient support under the applicable rule above is established. A material mismatch in restriction, scope, polarity, attribution, uncertainty, or evidentiary strength is a failed card, not a warning. For a failed card or warning, use `comments` only for a concise explanation of the mismatch or concern.
