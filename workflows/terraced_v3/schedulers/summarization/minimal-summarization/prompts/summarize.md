# Minimal terraced-v3 summarization

Convert the supplied locked cited fact ledger into concise report sentences without changing clinical meaning.

{{output_contract}}

Additional rules:
- preserve WHO5 wording and concurrent-diagnosis scope;
- use domains only: diagnosis, prognosis, treatment, biomarker, germline;
- do not emit headings; core renders headings deterministically.

# Locked cited facts
{{facts}}
