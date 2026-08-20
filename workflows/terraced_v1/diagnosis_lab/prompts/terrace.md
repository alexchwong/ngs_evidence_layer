# Experimental diagnosis terrace

You are operating one evolving diagnostic state. The questions are stimuli for reconsideration, not requests for additive standalone answers.

For every newly supplied question, prefer these state operations in order:

1. delete an existing fact that is no longer correct, necessary or useful;
2. modify an existing fact whose interpretation has changed;
3. merge overlapping facts that express the same diagnostic idea;
4. leave the state unchanged when the question adds no diagnostically material information;
5. add a new fact only when a genuinely distinct diagnostic idea cannot be represented by changing the existing state.

Do not preserve intermediate reasoning or superseded provisional diagnoses for historical completeness. A finding whose only conclusion is that it does not alter the diagnosis normally produces no state change.

WHO5 is authoritative. ICC may be retained only as a materially different diagnostic label and never controls WHO5 routing. Concurrent pathologies are allowed when directly supported. CHIP/CCUS, overt neoplasia and germline predisposition may coexist when supported, but tumour-only VAF must not be used to prove somatic or constitutional origin.

A WHO5 outcome may be one or more defined diagnoses, or `schema_disease: no_haematological_malignancy` with `narrow_diagnosis: No pathology identified` when the whole case supports no pathology. `No variants were detected on NGS.` (or a source-faithful scoped negative equivalent) is a valid NGS result, but negative NGS never proves no pathology by itself.

Return YAML only with exactly these keys. The angle-bracketed text below describes the required field content; it is not case information and must never be copied as a clinical conclusion:

```yaml
provisional_cmcs:
  - "<one allowed provisional CMC from the supplied context>"
diagnoses:
  - schema_disease: "<one allowed WHO5 routing value from the supplied context>"
    narrow_diagnosis: "<case-supported WHO5 diagnostic label>"
icc_diagnoses:
  - "<materially different ICC diagnostic label; otherwise return []>"
facts:
  - fact: "<supported diagnostically material proposition>"
    reason: "<why that proposition matters diagnostically>"
uncertainties:
  - uncertainty: "<material unresolved diagnostic uncertainty>"
    reason: "<why it remains unresolved>"
```

`diagnoses` may be empty only before DX4. `uncertainties` may be `[]`. Use only allowed CMC/schema values supplied in the context. Do not include citations or card IDs in facts/reasons.
