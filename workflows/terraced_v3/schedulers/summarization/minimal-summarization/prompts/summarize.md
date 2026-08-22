# Minimal terraced-v3 summarization

Convert the supplied locked cited fact ledger into concise report sentences without changing clinical meaning.

Return YAML only:

```yaml
sentences:
  - sentence_id: diagnosis-1
    domain: diagnosis
    sentence: "..."
    fact_ids: [who5-DX1]
```

Rules:
- every supplied surfaced fact_id must appear in at least one sentence;
- each sentence may use only fact_ids from its own domain;
- do not add any proposition not present in the supplied facts;
- preserve WHO5 wording and concurrent-diagnosis scope;
- use domains only: diagnosis, prognosis, treatment, biomarker, germline;
- sentence text must be plain prose, end in a full stop, and contain no card tags;
- do not emit headings; core renders headings deterministically.

# Locked cited facts
{{facts}}
