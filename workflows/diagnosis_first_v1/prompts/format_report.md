# Diagnosis-first final-summary synthesis

## Task

Transform retained `report-draft.yaml` content into the deterministic `report-summary.yaml` template. This is a structured summarisation step, not final Markdown formatting.

`report-draft.yaml` is the sole source of clinical report content. It contains only rules retained after deterministic omission filtering.

## Source integrity

- Do not introduce a clinical assertion, qualification, recommendation, patient fact, or citation absent from `report-draft.yaml`.
- Do not restore, discuss, or infer content from omitted rules; those rules are deliberately absent from this input.
- Compress, merge, split, and reorder retained statements only as needed to satisfy the selected formatting prompt.
- Preserve clinically material qualifications and uncertainty.
- Apply `workflows/diagnosis_first_v1/prompts/citation_rules.md` exactly.

## Section mapping

Populate the existing summary sections in this order:

- `detected_variants`: detected NGS variant summary;
- `diagnosis`: integrated WHO/ICC diagnosis and material diagnostic qualification;
- `prognosis`: applicable prognostic framework, risk and material variant effects;
- `treatment`: clinically actionable treatment implications;
- `mrd`: molecular MRD implications;
- `germline`: possible germline predisposition implications.

The deterministic renderer later emits non-empty sections in this order without adding section headings.

## Output contract

Modify only `report-summary.yaml`. Preserve `schema_version`, every top-level section name, and each section's `statements` key. Each completed statement must contain only `text` and `citation`. A section may contain zero statements; when it has no reportable content, either leave the pre-filled `text: ""` / `citation: ""` placeholder untouched or set `statements: []`.

Return no Markdown report, headings, bibliography, numeric citations, code fences, or commentary.
