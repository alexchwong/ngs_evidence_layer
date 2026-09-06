# Atomic patient-applicability audit

Independently assess only the supplied derived patient states and criterion applications.

Use only:
- the supplied structured patient facts and variant identities;
- literature rules that have already passed evidence review; and
- the exact reasoning items supplied for audit.

Do not search for evidence, select cards, revise literature rules, compare framework conclusions, or decide the final diagnosis/PTBG conclusion. Do not invent patient facts.

For every supplied item, return an audit row. Do not stop after finding the first error. Assess the complete batch before answering.

For a derived state:
- `supported`: the cited patient facts support the proposed value;
- `unsupported`: the cited patient facts contradict the proposed value;
- `indeterminate`: the supplied patient facts do not resolve the proposed value.

For a criterion:
- `met`: the evidence-approved rule is satisfied by the supplied patient facts/audited state;
- `not_met`: a required condition is contradicted or absent where absence is explicitly established;
- `unknown`: the supplied information does not resolve the criterion.

Return exactly:

```yaml
derived_states:
  - state_id: "<exact supplied state_id>"
    status: <supported|unsupported|indeterminate>
    value: "<audited value, or null when indeterminate>"
    case_fact_ids: ["<exact supplied fact IDs actually used>"]
    comments: ["<concise explanation; [] when no comment is needed>"]
criteria:
  - criterion_id: "<exact supplied criterion_id>"
    status: <met|not_met|unknown>
    case_fact_ids: ["<exact supplied fact IDs actually used>"]
    comments: ["<concise explanation; [] when no comment is needed>"]
```

Return no framework-level conclusion. Python evaluates formal logic and commit policy after this audit.
