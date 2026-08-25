# Pair settled clinical statements to the reduced evidence bundle

The clinical statements and their reasons are already settled. Do not rewrite them.
For each candidate, select only the local `CARD nn` blocks whose interpretation reasonably supports the statement when the patient observations in the reason are treated as given.

Do not select a card merely because it mentions the same gene or disease. It must support the clinical conclusion in the statement.
If no supplied card reasonably supports a statement, return an empty `card_refs` list.

{{output_contract}}

# Settled statements
```yaml
{{statements}}
```

# Reduced evidence bundle
{{cards}}
