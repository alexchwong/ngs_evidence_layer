# Generic post-evidence reasoning check

Evidence processing has removed one or more premises that were explicitly linked to clinical conclusions. Reassess only the affected conclusions from the surviving and removed stated premises.

Do not use outside medical knowledge, a corpus, or evidence cards. Do not invent a replacement premise. Do not reassess unaffected conclusions.

Use exactly one verdict per supplied item:
- `survives`: the original conclusion still follows from the surviving stated premises without changing its wording or attribution.
- `survives_with_qualification`: the core conclusion can remain only if an unsupported attribution or qualification is removed.
- `revise`: the surviving stated premises no longer support the conclusion.

Return exactly one YAML mapping:

```yaml
verdicts:
  - owner: <copy supplied owner>
    conclusion_id: <copy supplied conclusion_id>
    verdict: <survives|survives_with_qualification|revise>
    comments: []
```

Affected conclusions only:
{{ input.postcheck_items }}

Reasoning-2 artifact feedback from a prior attempt (null on first pass):
{{ input.postcheck_feedback }}

If feedback is supplied, repair only the stated structured-output defect and return all required affected-conclusion verdicts.
