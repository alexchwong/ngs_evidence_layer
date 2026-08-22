# Final sentence-to-fact semantic alignment

Semantically match every indexed report sentence to one or more supplied locked facts in the same clinical domain.

{{output_contract}}

Additional rules:
- use the supplied sentence manifest as authoritative; do not recreate, renumber, omit or reorder sentence IDs;
- return exactly one alignment row for every supplied sentence manifest row, preserving order;
- do not falsely attach an omitted fact to an unrelated sentence merely to force coverage;
- do not copy prose, reasons, citations or card tags into the output;
- do not create new clinical content.

# Supplied sentence manifest
```yaml
{{sentence_manifest}}
```

# Draft report
{{draft}}

# Locked surfaced facts
```yaml
{{facts}}
```
