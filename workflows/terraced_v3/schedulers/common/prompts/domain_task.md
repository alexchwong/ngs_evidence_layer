# Terraced-v3 typed clinical task

Fill the supplied clinical-statement proforma using only the immutable case, settled WHO5 diagnoses, final CMC context, assay scope and evidence cards. Do not write report prose beyond the requested surfaced `statement` fields.

General rules:
- answer every required decision row exactly once;
- keep each decision scoped to its supplied diagnosis context; do not transfer evidence from one concurrent disease to another;
- `statement` and `reason` are mandatory only when `surface: true`; when `surface: false`, both must be null;
- `reason` is a short auditable clinical justification, not hidden chain-of-thought;
- `case_refs` are exact C#/V# patient-source IDs from the structured case that the surfaced proposition relies on;
- citation pairing is a separate downstream step; return every `card_tags` / `target_card_tags` / `resistance_card_tags` field as `[]` in this clinical reasoning pass;
- make each surfaced `statement` one atomic answer to the domain question; do not surface a statement that merely repeats a case observation; put those observations in `reason`;
- if a previously returned surfaced statement remains correct, preserve its `statement` text and `case_refs` exactly rather than paraphrasing it; evidence provenance is assigned separately downstream;
- do not mutate diagnosis, CMC, variant IDs or gene symbols;
- do not add outside literature or web knowledge;
- return YAML only with exactly the task-specific schema.
