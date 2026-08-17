# Diagnosis-first YAML citation rules

Citation provenance is statement-level. Keep citation data separate from prose.

## Rule-draft YAML contract

This contract applies to `report-draft-dx.yaml` and `report-draft-remainder.yaml`.

- Do not create a new document. Modify the deterministic YAML template supplied by the evidence-gathering step.
- Preserve every rule `id` exactly and in order. Never add, delete, rename, or reorder rules.
- Every rule MUST contain at least one item under `statements`, including rules with `omit: true`.
- Use `omit: false` or `omit: No` for content that corresponds to `REPORT:` under the shared reporting policy.
- Use `omit: true` or `omit: Yes` for content that corresponds to `OMIT:`. The deterministic Step 6A assembly removes these rules completely.
- Each `statements` item is one atomic patient-level assertion with exactly two fields:
  - `text`: report-ready prose without any citation marker;
  - `citation`: the exact citation disposition for that assertion.
- The citation disposition is either adjacent exact runtime card markers, e.g. `[card:a1b2c3][card:d4e5f6]`, or the quoted YAML string `"(no citation required)"`.
- Different assertions supported by different cards MUST be separate statement items rather than one combined statement with the union of unrelated citations.
- A statement may cite more than one card only when every cited card directly supports that same assertion.
- Use only runtime card tags exposed in the evidence file permitted for that model step. Never create, infer, alter, shorten, translate, or renumber a runtime tag.
- Never put `[card:...]` or `(no citation required)` inside `text`.
- `R0.1` is mandatory retained patient-result content: keep `omit: false` and `(no citation required)`.

## Step-6B summary YAML contract

This contract applies to `report-summary.yaml`.

- Preserve the deterministic top-level section names and `statements` structure.
- Each completed statement has exactly `text` and `citation`.
- Write one complete report sentence per statement.
- Copy or combine only facts present in retained `report-draft.yaml` rules.
- When merging source statements, set `citation` to the union of the exact source citation markers needed for the retained facts.
- When splitting a source statement, each new statement inherits the exact citation disposition needed for the facts it retains.
- Never cite a runtime card tag that is absent from retained `report-draft.yaml`.
- Any section may contain zero statements. If a section has no reportable content, either leave its original `text: ""` / `citation: ""` placeholder untouched or set `statements: []`.
