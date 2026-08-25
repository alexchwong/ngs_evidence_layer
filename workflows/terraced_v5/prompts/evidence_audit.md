{{ include "includes/audit_general.md" }}

# Statement/reason versus evidence audit

Audit EVERY selected quote/card against BOTH the clinical statement and the reason used to justify it.

For each item decide:
- `quote_supports_statement`: does the quote affirmatively support the actual statement being made?
- `quote_supports_reason`: does the quote support the stated reason?

A card about a different clinical use of the same gene is not support for this claim. Absence of contrary evidence is not affirmative support.

Use `risk: warning` for non-gating fidelity/strength/context concerns when both support checks still pass. Give concise comments explaining any failure or warning. Do not prescribe a replacement clinical answer.

Return YAML only, preserving evidence IDs and order:
```yaml
audits:
  - evidence_id: E0001
    quote_supports_statement: true
    quote_supports_reason: true
    risk: none
    comments: []
```
