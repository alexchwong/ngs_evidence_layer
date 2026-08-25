---
id: core.statements.cited
semantic_type: clinical.statements.cited
format: yaml
provides:
  - statements[].statement_id
  - statements[].domain
  - statements[].statement
  - statements[].reason
  - statements[].case_refs
  - statements[].card_tags
requires: []
runtime_invariants: [immutable_statement_reason_and_provenance, local_evidence_check_before_acceptance]
---
# Active immutable cited statement ledger

Only reportable conclusions that answer their clinical-domain question enter this ledger. Patient observations are premises recorded in `reason` and referenced by `case_refs`; they are not independent reportable statements.

```yaml
statements:
  - statement_id: S0001
    domain: diagnosis
    statement: "WHO5 classification: AML, myelodysplasia-related."
    reason: "The marrow has AML-range blasts with qualifying myelodysplasia-related mutations."
    case_refs: [C2, V1]
    card_tags: ["[card:0123456789ab]"]
```

Literature citations attach to the `statement`. Evidence review evaluates the statement together with its reason, treating the patient observations represented by `case_refs` as supplied premises.
