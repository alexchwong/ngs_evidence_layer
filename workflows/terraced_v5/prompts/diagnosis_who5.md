{{ include "includes/diagnosis_criterion_checks.md" }}

# Terraced-v5 WHO5 diagnosis

Classify the case according to WHO 5th Edition only, using only the supplied case and WHO5 authority cards.

Return every concurrent WHO5 diagnosis separately if present. Patient facts may be premises. Do not choose final citations in this pass.

Use only an exact supplied WHO5 `schema_disease` value. Do not write CMC values; core derives CMCs deterministically from WHO5 schema disease.

Return YAML only:
```yaml
diagnoses:
  - schema_disease: "<allowed schema disease>"
    status: "established | conditional | indeterminate"
    diagnosis: "<WHO5 diagnostic label>"
    criteria:
      - authority_card_id: "<exact supplied authority card ID>"
        criterion_type: "molecular_membership | other"
        criterion: "<one discrete authority-backed diagnostic criterion>"
        reason: "<why this criterion contributes to the diagnosis>"
        checks:
          positive_supportive: [v01]
          negative_supportive: []
          indeterminate: []
          not_contributory: []
```
