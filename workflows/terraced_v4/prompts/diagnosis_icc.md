# Terraced-v4 ICC diagnosis

Classify the case according to ICC only, using only the supplied case and ICC authority cards.

The authoritative WHO5 result is supplied for comparison only. Do not alter or reinterpret the WHO5 result. First make the ICC classification according to ICC. Then state whether the resulting ICC classification is significantly different from WHO5 and explain the clinically meaningful difference, if any.

For each ICC diagnosis provide one or more granular reasons. Each reason should be one independently understandable proposition. Do not choose citations in this pass.

Return YAML only:
```yaml
diagnoses:
  - status: "established | indeterminate"
    diagnosis: "<ICC diagnostic label>"
    reasons:
      - "<granular reason>"
comparison_with_who5:
  significantly_different: false
  explanation: "<clinically meaningful comparison>"
```
