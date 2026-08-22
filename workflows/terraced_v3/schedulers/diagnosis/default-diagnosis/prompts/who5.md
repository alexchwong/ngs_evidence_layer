# WHO5 diagnosis state

Determine the WHO 5th Edition diagnosis or concurrent diagnoses from the supplied case and diagnostic evidence. WHO5 alone controls downstream disease routing. Do not perform ICC classification.

{{output_contract}}

Additional task rules:
- supporting and contradicting rows are patient-level propositions relevant to the returned diagnosis set, not generic literature summaries;
- absence of a card is not evidence that a case fact is absent;
- `card_tags` are the final claimed evidence provenance for each returned fact: use only exact supplied card tags that directly support the complete proposition; use `[]` only for a genuinely case-derived proposition that does not depend on a literature card;
- keep each returned fact to one atomic reportable proposition wherever practical;
- on reconsideration, if a previously validated fact remains correct, copy its `fact` text and `card_tags` exactly; do not paraphrase an unchanged fact. Change either only when the proposition or its evidence provenance truly changes;
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
