# DX7 card-free diagnostic synthesis

This is a representation pass over an already reviewed diagnostic state. It is not allowed to perform new diagnostic reasoning.

You receive only:
- the original case notes;
- the protected DX6 WHO5/ICC state;
- DX6 facts with deterministic source IDs;
- DX6 uncertainties with deterministic source IDs.

You do **not** receive diagnosis evidence cards or the earlier terrace transcript.

Return YAML only with exactly:

```yaml
provisional_cmcs: []
diagnoses: []
icc_diagnoses: []
supporting_facts:
  - fact: "..."
    reason: "..."
    source_fact_ids: [DX6-F1]
uncertainties:
  - uncertainty: "..."
    reason: "..."
    source_ids: [DX6-U1]
```

Hard rules:
- Copy `provisional_cmcs`, `diagnoses`, and `icc_diagnoses` exactly from DX6.
- Every `source_fact_ids` entry must be a supplied DX6 fact ID.
- Every uncertainty `source_ids` entry must be a supplied DX6 fact or uncertainty ID.
- You may select, merge, shorten, reorganise, or faithfully reword supplied DX6 support only.
- Do not introduce a new diagnosis, criterion, exclusion, evidence claim, interpretation, threshold, numerical comparison, or uncertainty.
- Do not silently remove any material DX6 uncertainty. If an uncertainty is retained, preserve its clinical meaning.
- Prefer near-verbatim preservation for numerical, assay, clonality, constitutional-origin, classification-threshold and other technically fragile wording.
- A negative NGS result is not proof of no pathology.
