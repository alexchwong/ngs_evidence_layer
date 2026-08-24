{{ include "includes/audit_general.md" }}

# Statement/proforma preservation audit

Audit EVERY generated statement against the supplied validated proforma element.

The validated proforma and its supplied authority-backed criteria are authoritative for this stage. Do NOT independently re-diagnose the case, introduce classification rules from model knowledge, or require exclusions/criteria absent from the supplied validated context.

Assess:
1. `statement_represents_proforma`
   - true only when the statement preserves the supplied conclusion, scope, status/conditionality, framework, qualifiers, and molecular relationships;
   - false if it adds, removes, strengthens, weakens, reverses, generalises, or invents any qualifier or relationship.
2. `reasoning_status`
   - `supported`: the rendered reasons faithfully represent the supplied validated proforma/criteria;
   - `supported_if`: the validated proforma itself is explicitly conditional on a supplied unresolved/presumed-negative dependency;
   - `unsupported`: only when the rendered reasons contradict or fail to represent the supplied validated proforma/criteria.

For diagnosis elements:
- do not judge whether the validated diagnosis is medically correct or sufficient;
- do not replace or downgrade the diagnosis label;
- do not invent additional diagnostic prerequisites;
- use the supplied testing-state rules and authority context exactly as given;
- an unreported gene on the configured complete NGS panel is a verified negative;
- an absent/pending non-NGS test is presumed negative/normal only when the validated criterion explicitly depends on it;
- a supplied non-pending case fact is observed, not indeterminate.

When a statement is not acceptable, give concise `issues` and `negative_guidance`. Negative guidance must describe only the representation mistake that must not recur; do not prescribe a new diagnosis or clinical answer.

Return YAML only, preserving schema IDs and order:
```yaml
audits:
  - schema_id: "PX-ADVERSE-01"
    statement_represents_proforma: true
    reasoning_status: supported
    issues: []
    negative_guidance: []
```
