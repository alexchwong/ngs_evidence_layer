# ICC diagnostic owner — atomic reasoning

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

Use only the supplied ICC owner pack. Assess ICC independently; do not assume that a WHO conclusion is correct.

Rules:
- Patient observations are immutable. Reference supplied `case_fact_ids` and `variant_ids`; do not invent patient facts.
- `rules` are atomic ICC/literature propositions and may use only genuinely supporting supplied card tags.
- `derived_states` are optional patient-specific inferences from supplied facts and are evidence-free patient reasoning objects.
- `criteria` apply rules to this patient. `logic` uses only shallow `all_of` / `any_of` groups; Python evaluates it.
- Use `I-` prefixes for all stable reasoning IDs.
- `proposal.status` is `established`. `proposal.schema_disease` is normally null, except `no_haematological_malignancy` when that is the explicit ICC outcome.
- Return variant assessments for every supplied variant.
- A refined/superseded diagnosis requires a non-null defining `root_id`.

## Deterministic feedback from a prior rejected owner attempt
{{ input.audit_feedback }}

## Owner pack
{{ input.owner_pack }}
