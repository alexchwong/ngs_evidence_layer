# Germline predisposition

Assess whether the NGS findings TOGETHER WITH the supplied clinical picture support a germline predisposition syndrome.

The clinical picture includes only information actually supplied in the case, such as age, personal history, family history, phenotype, and prior malignancies. Do not interpret an isolated molecular finding as sufficient clinical germline support unless the supplied evidence explicitly permits that conclusion.

Classify every supplied variant once:
- `germline_support`: molecular finding plus clinical picture support consideration of a germline syndrome.
- `germline_against`: integrated molecular and clinical picture argue against a germline syndrome.
- `germline_uncertain`: available molecular/clinical information is insufficient for either conclusion.

`reason` must integrate molecular evidence and the supplied clinical context. Do not recommend testing, referral, or counselling.

Return YAML only:
```yaml
germline_support: []
germline_against: []
germline_uncertain: []
```

Rows use:
```yaml
- variants: [v01]
  reason: "<one integrated molecular + clinical proposition>"
```
