# Final sentence-to-fact semantic alignment

Semantically match every indexed report sentence to one or more supplied locked facts in the same clinical domain.

{{output_contract}}

Additional rules:
- include every supplied sentence ID exactly once and preserve order;
- do not falsely attach an omitted fact to an unrelated sentence merely to force coverage;
- do not copy prose, reasons, citations or card tags into the output;
- do not create new clinical content.

# Draft report
{{draft}}

# Locked surfaced facts
```yaml
{{facts}}
```
