# WHO5 diagnosis state

Determine the WHO 5th Edition diagnosis or concurrent diagnoses from the supplied case and diagnostic evidence. WHO5 alone controls downstream disease routing. Do not perform ICC classification.

{{output_contract}}

Additional task rules:
- absence of a card is not evidence that a case fact is absent;
- `case_refs` are exact C#/V# patient-source IDs from the structured case that the proposition relies on;
- `card_refs` pair each literature-dependent statement to the supplied local `CARD nn` evidence blocks; do not write runtime or source card IDs;
- return only diagnosis statements; patient findings, supporting premises and limitations belong in `reason`, not as separate reportable rows;
- `statement` must directly answer the WHO5 diagnosis question and must be exactly `WHO5 classification: <diagnosis>.` using the same diagnostic label from the row;
- on reconsideration, if a previously validated statement remains correct, copy its `statement`, `reason`, `case_refs`, and `card_refs` exactly. Change them only when the conclusion, justification, or evidence provenance truly changes;
- do not write CMC values.

# Structured immutable case
```json
{{case}}
```

# Allowed WHO5 schema diseases
{{allowed_who5_diseases}}

# NGS assay scope
{{panel_scope}}

# Cumulative diagnosis evidence
{{evidence}}

# Prior validated WHO5 state
{{prior_state}}

# Current pass
{{phase_instruction}}
