# Terraced-v3 typed clinical task

Fill the supplied hard-fact proforma using only the immutable case, settled WHO5 diagnoses, final CMC context, assay scope and evidence cards. Do not write report prose beyond the requested surfaced `fact` fields.

General rules:
- answer every required decision row exactly once;
- keep each decision scoped to its supplied diagnosis context; do not transfer evidence from one concurrent disease to another;
- `fact` and `reason` are mandatory only when `surface: true`; when `surface: false`, both must be null;
- `reason` is a short auditable clinical justification, not hidden chain-of-thought;
- `case_refs` are exact C#/V# patient-source IDs from the structured case that the surfaced proposition relies on;
- `card_tags` are the final claimed literature evidence provenance for each surfaced fact: use only exact supplied card tags that directly support the complete proposition; pure patient observations should normally use `card_tags: []`; literature-dependent interpretations must carry supporting cards;
- make each surfaced `fact` one atomic reportable proposition wherever practical;
- if a previously returned surfaced fact remains correct, preserve its `fact` text, `case_refs`, and `card_tags` exactly rather than paraphrasing it; change either only when the clinical proposition or its evidence provenance truly changes;
- do not mutate diagnosis, CMC, variant IDs or gene symbols;
- do not add outside literature or web knowledge;
- return YAML only with exactly the task-specific schema.
