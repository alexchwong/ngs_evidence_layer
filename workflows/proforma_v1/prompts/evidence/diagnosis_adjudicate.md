# WHO1 diagnostic evidence adjudication

For each disputed WHO1 diagnostic fact/card pair, decide only whether the supplied card is sufficient support for the proposed WHO5 diagnostic proposition under the diagnosis-complete-support policy.

For a primary-diagnosis proposition, require the card to support the relevant defining diagnostic proposition when applied to the supplied case facts.

For a concurrent-pathology proposition, apply compositional support. The supplied case facts may establish the patient-specific findings suggesting a separate pathology, while the card supplies the disease-specific molecular premise. The card does not need to describe the exact co-occurrence with the primary disease or independently prove the second diagnosis. Include the card when it supports that the variant is a hallmark, defining molecular subset, diagnostic criterion, useful discriminator/differential marker, or other strong clinically meaningful signal for the named distinct disease, disease family, or lineage, provided the proposition does not overstate what the card and supplied case facts together justify. Do not exclude a card merely because it does not state that the second pathology can coexist with the primary disease.

Consider the supplied case facts together with defining criteria, thresholds, exclusions, precedence/supersession, finite gene-set membership, schema disease and routing consequence where applicable. Preserve all material restrictions in the diagnostic rule and its application, including where relevant allelic state, variant class, threshold, disease/subtype, co-mutation or exclusion context, cytogenetic context, population, framework/classification system, polarity, uncertainty, and evidentiary strength. A narrower or differently scoped card must be excluded when the proposed diagnostic proposition drops or changes a required restriction. Ordinary paraphrase is acceptable when the diagnostic meaning and restrictions are unchanged.

A defining criterion or threshold can support an exclusion when combined with a supplied case fact. Likewise, a disease-specific molecular association can support a concurrent-pathology suspicion when combined with supplied patient findings. Do not rewrite the diagnosis, introduce another card, or select evidence outside the disputed pair.

Each supplied dispute contains a deterministic `dispute_id`. Copy that supplied ID exactly to identify your answer; do not derive or renumber IDs from row position. Do not reproduce evidence IDs or card tags in the output. You may return the answer rows in any order. Return exactly one answer for every supplied dispute ID; do not omit, duplicate, modify, or invent IDs.

Return YAML only in this exact shape:
```yaml
adjudications:
  - dispute_id: D0001
    decision: include
    reason: "<one concise reason for the adjudication>"
```
