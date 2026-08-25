{{ include "includes/diagnosis_criterion_checks.md" }}

# Terraced-v5 ICC diagnosis

Classify the case according to ICC only, using only the supplied case and ICC authority cards.

The authoritative WHO5 result is supplied for comparison only. Do not alter or reinterpret the WHO5 result. First make the ICC classification according to ICC. Then state whether the resulting ICC classification is significantly different from WHO5 and explain the clinically meaningful difference, if any.

For each ICC diagnosis, apply the supplied authority cards using the criterion-check structure. Do not choose final citations in this pass.

Return YAML only:
```yaml
diagnoses:
  - status: "established | conditional | indeterminate"
    diagnosis: "<ICC diagnostic label>"
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
comparison_with_who5:
  significantly_different: false
  explanation: "<clinically meaningful comparison>"
```
