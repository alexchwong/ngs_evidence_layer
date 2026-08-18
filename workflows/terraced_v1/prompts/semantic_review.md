# Terraced-v1 semantic review

Independently review the completed category answer. This is a high-threshold safety review, not a style editor.

Return JSON only:

```json
{"pass": true, "issues": []}
```

or, only for a material clinical defect:

```json
{"pass": false, "issues": ["concise actionable defect"]}
```

Fail only for a clear material problem such as contradiction with the case, contradiction between facts, wrong disease/framework application, an unmet premise that changes the conclusion, incorrect WHO5 routing, or a material misinterpretation of supplied evidence. Do not fail for citation absence, minor wording preferences, harmless incompleteness, or because a negative/absence-of-evidence conclusion has no positive card.

Do not rewrite the answer. The owning answering conversation will reconsider the complete category state if repair is required.
