# Independent second-diagnosis owner — atomic reasoning

## Output serialization contract
Return exactly one YAML mapping conforming to the declared schema. Return YAML only: no Markdown headings, no tables, no prose outside the mapping, no code fence around the answer, and no `---` document separators. The example below shows serialization/shape only; replace placeholders with your actual answer.

```yaml
authority: <who5|icc|second_diagnosis>
proposal:
  proposal_id: <stable ID>
  label: <diagnosis label>
  kind: <diagnosis|second_diagnosis>
  schema_disease: <string or null>
  diagnostic_effect: <unchanged|refined|superseded>
  variant_ids: []
  variant_assessments:
    - variant_id: <exact supplied variant ID>
      classification: <diagnostic_for_primary|nonspecific|diagnostic_for_other_pathology>
      other_pathology: null
      reason: <reason>
  status: <established|signal|none>
rules:
  - rule_id: <stable rule ID>
    statement: <one atomic literature/framework rule>
    evidence_required: true
    evidence_card_tags: []
derived_states: []
criteria:
  - criterion_id: <stable criterion ID>
    rule_ids: []
    case_fact_ids: []
    variant_ids: []
    state_ids: []
    proposed_status: <met|not_met|unknown>
logic: []
root_id: null
reason: <concise integrated reason>
```

Assess whether the supplied case establishes a concurrent/second haematological diagnosis. Do not merely copy a WHO or ICC variant-assessment suggestion.

Rules:
- Use only supplied case facts, variants and candidate cards.
- `proposal.kind` must be `second_diagnosis` and all stable IDs must use the `S-` prefix.
- `proposal.status` is one of: `established`, `signal`, `none`.
- Use `established` only when the complete defining rule is evidence-supported and the supplied patient facts satisfy it.
- Use `signal` when a finding warrants consideration but the supplied facts do not establish the diagnosis.
- `none` means no concurrent diagnosis is proposed.
- Literature rules and patient applicability must be separated into `rules`, optional `derived_states`, and `criteria`.
- If status is `established`, provide a defining `root_id`. `signal` and `none` may use null when no full defining root is claimed.
- Card assignments may use only the supplied candidate-card envelope.

## Deterministic feedback from a prior rejected owner attempt
{{ input.audit_feedback }}

## Owner pack
{{ input.owner_pack }}
