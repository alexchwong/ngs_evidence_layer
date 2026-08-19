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

Fail only for a clear material problem such as contradiction with the case, contradiction between facts, wrong disease/framework application, an unmet premise that changes the conclusion, incorrect WHO5 routing, a material misinterpretation of supplied evidence, or omission of a directly supported clinically actionable conclusion required by the reporting questions. Do not fail for citation absence, minor wording preferences, genuinely harmless incompleteness, or because a negative/absence-of-evidence conclusion has no positive card.

For MRD, distinguish identifying a prospective marker and establishing its diagnostic baseline from assigning MRD status on a post-treatment specimen. If a diagnostic specimen contains a validated disease-specific marker, the completed answer must explicitly identify that marker in a standalone positive fact and preserve any supported baseline or monitoring recommendation. Merely implying marker suitability through a baseline recommendation, or replacing the positive marker conclusion with generic no-current-MRD prose, is a material defect; lack of serial kinetics, quantitative follow-up levels or follow-up assay sensitivity limits current MRD-status interpretation only.

Also fail when a reportable positive marker or baseline recommendation is combined in the same fact with a routine negative or unavailable-result statement in a way that obscures the positive conclusion or makes the whole fact liable to negative-reportability quarantine. Prefer the appropriate positive MRD marker over separate lists of detected alterations that are unsuitable for MRD unless such a caution independently changes patient management.

Do not rewrite the answer. The owning answering conversation will reconsider the complete category state if repair is required.
