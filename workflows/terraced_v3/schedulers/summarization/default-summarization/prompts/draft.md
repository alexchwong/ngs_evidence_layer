# Terraced-v3 final synthesis

Perform lossless semantic compression of the supplied locked cited fact ledger into an uncited clinical interpretative report. Clinical decisions are already frozen; do not reconsider them.

Requirements:
- represent every supplied surfaced fact at least once; merging overlapping facts is allowed only if all semantic content is preserved;
- do not add an assertion not represented by a supplied fact;
- use concise patient-level prose for clinical haematologists;
- diagnosis prose must preserve WHO5 wording; include the independent ICC diagnosis when supplied, without letting ICC replace WHO5;
- preserve concurrent diagnoses and disease scope;
- use exact standalone bold headings only: `**Diagnosis**`, `**Prognosis**`, `**Treatment Implications**`, `**MRD**`, `**Germline**`;
- omit a heading if no supplied fact belongs to that domain;
- put each sentence on its own line and end each sentence with a full stop;
- do not write citations, card tags, fact IDs, reasons, or machine-state field names.

# Locked surfaced facts
```yaml
{{facts}}
```

{{correction}}
