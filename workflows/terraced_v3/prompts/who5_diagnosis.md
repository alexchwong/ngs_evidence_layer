# WHO5 diagnosis state

Determine the WHO 5th Edition diagnosis or concurrent diagnoses from the supplied case and diagnostic evidence. WHO5 alone controls downstream disease routing. Do not perform ICC classification.

Return YAML only with exactly these top-level keys:

```yaml
diagnoses:
  - diagnosis_id: DX1
    schema_disease: AML
    status: established
    diagnosis: "..."
    fact: "According to WHO5, ... ."
    reason: "Short auditable clinical justification."
    candidate_card_tags: ["[card:0123456789ab]"]
supporting_facts:
  - diagnosis_ids: [DX1]
    fact: "... ."
    reason: "..."
    candidate_card_tags: []
contradicting_facts:
  - diagnosis_ids: [DX1]
    fact: "... ."
    reason: "..."
    candidate_card_tags: []
```

Rules:
- use only the supplied allowed canonical `schema_disease` values;
- return each concurrent WHO5 pathology separately (for example, a myeloid neoplasm and CLL/SLL may coexist);
- assign sequential diagnosis IDs DX1, DX2, ... in clinical prominence order;
- use status only `established` or `indeterminate`; do not create rows merely to list excluded diagnoses;
- the diagnosis `fact` must be reportable, end with a full stop, and state WHO5 authority explicitly;
- supporting and contradicting facts must be patient-level propositions relevant to the returned diagnosis set, not generic literature summaries;
- supporting/contradicting rows may scope to one or multiple returned diagnosis IDs;
- every surfaced fact has a short reason;
- candidate card tags are non-authoritative hints and must use only supplied tags;
- absence of a card is not evidence that a case fact is absent;
- do not write CMC values. Python derives CMC only after this output validates.
