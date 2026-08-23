# Terraced-v5 WHO5 diagnosis

Classify the case according to WHO 5th Edition only, using only the supplied case and WHO5 authority cards.

Return every concurrent WHO5 diagnosis separately if present. For each diagnosis provide one or more granular reasons. Each reason should be one independently understandable proposition. Patient facts may be premises. Do not choose citations in this pass.

Use only an exact supplied WHO5 `schema_disease` value. Do not write CMC values; core derives CMCs deterministically from WHO5 schema disease.

Return YAML only:
```yaml
diagnoses:
  - schema_disease: "<allowed schema disease>"
    status: "established | indeterminate"
    diagnosis: "<WHO5 diagnostic label>"
    reasons:
      - "<granular reason>"
```
