# Fact/reason to card evidence alignment

For each supplied surfaced clinical fact, select the evidence card tag(s) that genuinely support the stated reason sufficiently to justify the fact.

{{output_contract}}

Additional rules:
- include every supplied fact ID exactly once in supplied order;
- candidate tags are hints only: verify them; replace or omit them when inappropriate;
- treat the reason as the semantic bridge: a card must support the reason, and that reason must be sufficient for the fact;
- case-derived facts may correctly receive null;
- do not alter facts, reasons, decisions, IDs, or diagnosis scope;
- do not add commentary.
