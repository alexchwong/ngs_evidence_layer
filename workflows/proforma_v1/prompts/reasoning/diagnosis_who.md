# WHO5 diagnostic owner — atomic reasoning

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

Use only the supplied owner pack. Produce one WHO5 proposal and the smallest complete atomic reasoning graph needed to support it.

Rules:
- Patient observations are immutable. Reference supplied `case_fact_ids` and `variant_ids`; do not invent new patient facts.
- `rules` are literature/framework propositions. State each rule atomically and assign only genuinely supporting `evidence_card_tags` from this owner's candidate-card envelope. Use `[]` when no supplied card supports the rule.
- `derived_states` are optional patient-specific semantic inferences from supplied facts. Do not cite literature cards to a derived state.
- `criteria` apply evidence-backed rules to supplied patient facts/states. `proposed_status` is your proposed patient applicability, not the final audit result.
- `logic` may use only shallow `all_of` / `any_of` groups. Python evaluates the final graph.
- Use `W-` prefixes for every proposal/rule/state/criterion/logic ID.
- WHO5 `proposal.schema_disease` must be populated. `proposal.status` is `established` for the proposed WHO diagnosis.
- Return variant assessments for every supplied variant using the existing diagnostic classifications.
- If the diagnosis is refined or superseded, `root_id` must identify the defining criterion/logic root. If unchanged and no defining molecular criterion is claimed, `root_id` may be null.

## Deterministic feedback from a prior rejected owner attempt
{{ input.audit_feedback }}

## Owner pack
{{ input.owner_pack }}
