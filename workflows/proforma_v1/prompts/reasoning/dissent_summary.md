# User-facing decision summary

## Output serialization contract
Return exactly one YAML mapping conforming to the declared schema. Return YAML only: no Markdown headings, no tables, no prose outside the mapping, no code fence around the answer, and no `---` document separators. The example below shows serialization/shape only; replace placeholders with your actual answer.

```yaml
summary: <concise plain-English summary>
highlights:
  - decision_id: <exact ledger decision_id>
    disposition: <kept|revised|dropped|unresolved|not_reportable>
    explanation: <ledger-faithful explanation>
```

Summarise the supplied immutable decision ledger in plain English for a report user.

Explain the major conclusions considered and what was kept, revised, dropped or left unresolved. Highlight clinically important exclusions and the facts/evidence that drove them.

Constraints:
- Make no new clinical judgment.
- Do not change any disposition.
- Every highlight must reference an existing decision_id and repeat its exact disposition.
- Keep the summary concise and understandable without requiring the user to inspect raw model artifacts.

## Decision ledger
{{ input.decision_ledger }}
