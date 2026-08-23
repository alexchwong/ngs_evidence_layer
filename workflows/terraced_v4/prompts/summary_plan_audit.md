# Summary-plan semantic-preservation audit

Audit the proposed combination plan against the ORIGINAL reportable sentences.

This audit occurs before paraphrasing. Its purpose is to detect information loss introduced by omission or by combining several source sentences into one draft sentence.

Set `preserved: false` if any planned draft sentence materially loses, reverses, overstates or adds a clinical proposition from its `source_statement_ids`, or if an omitted statement contains material information that is not safely represented elsewhere.

Pay particular attention to qualifying facts that explain WHY a classification applies (for example defining molecular findings, thresholds, or framework-specific qualifiers). A draft that preserves only the diagnostic label but drops its material basis is not preserved.

Do not reject harmless wording compression, grammar changes, or removal of true redundancy.

When `preserved: false`, give specific actionable issues. Name the affected planned sentence ID or omitted statement ID in `target` and state exactly what information was lost/altered.

Return YAML only:
```yaml
preserved: true
issues: []
```

Failure example:
```yaml
preserved: false
issues:
  - target: diagnosis-1
    issue: "The combined draft retains the AML-MR label but drops S0001's qualifying SRSF2 and ASXL1 molecular basis."
```
