# Terraced-v3 typed clinical task

Fill the supplied hard-fact proforma using only the immutable case, settled WHO5 diagnoses, final CMC context, assay scope and evidence cards. Do not write report prose beyond the requested surfaced `fact` fields.

General rules:
- answer every required decision row exactly once;
- keep each decision scoped to its supplied diagnosis context; do not transfer evidence from one concurrent disease to another;
- `fact` and `reason` are mandatory only when `surface: true`; when `surface: false`, both must be null;
- `reason` is a short auditable clinical justification, not hidden chain-of-thought;
- candidate card tags are hints only and must be exact supplied tags; an independent alignment pass decides final citations;
- do not mutate diagnosis, CMC, variant IDs or gene symbols;
- do not add outside literature or web knowledge;
- return YAML only with exactly the task-specific schema.
