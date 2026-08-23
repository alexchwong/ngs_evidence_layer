{{ include "includes/audit_general.md" }}

# Statement/reason semantic audit

Audit EVERY generated statement against its source proforma proposition and reasons.

Assess two things:
1. `statement_represents_proforma`: the statement contains only the conclusion actually represented by the proforma, without adding, strengthening, reversing, or generalising it.
2. `reasoning_status`: whether the supplied reason(s) justify the statement as written.
   - `supported`: justified directly.
   - `supported_if`: already-supported conclusion is appropriately conditional on a genuinely unresolved discriminator/exclusion.
   - `unsupported`: the reasoning does not justify the statement, including when a condition would have to invent missing positive defining evidence.

When a statement is not acceptable, give concise `issues` and `negative_guidance`. Do not prescribe the replacement answer.

Return YAML only, preserving schema IDs and order:
```yaml
audits:
  - schema_id: "PX-ADVERSE-01"
    statement_represents_proforma: true
    reasoning_status: supported
    issues: []
    negative_guidance: []
```
