# Terraced-v1 reportability fact-structure classifier

Classify the structure of every accepted clinical fact. Do not decide whether the fact should be reported. Deterministic code applies the reportability policy after this pass.

Return exactly one row for every supplied `fact_id`, preserving supplied order:

```yaml
classifications:
  - fact_id: diagnosis-1
    molecular: true
    targets: [NPM1]
    polarity: not_a_result
    negative_consequence: false
  - fact_id: prognosis-2
    molecular: true
    targets: [TP53]
    polarity: not_detected
    negative_consequence: true
  - fact_id: treatment-1
    molecular: false
    targets: []
    polarity: not_a_result
    negative_consequence: false
```

Classify only these four observations for each fact:

1. `molecular`: `true` only when the fact makes a patient-level claim about one or more specific molecular targets. Generic disease management, generic clinical recommendations, morphology-only conclusions, and non-molecular score statements are `false`.
2. `targets`: every specific molecular target central to the claim. Use canonical gene or named fusion/rearrangement level, not HGVS detail. Examples: `NPM1`, `TP53`, `BCR::ABL1`, `PML::RARA`, `FLT3`. Use `[]` when `molecular: false`.
3. `polarity`: use exactly one of:
   - `detected` — the fact's patient-level claim is directly that the molecular finding was detected/present;
   - `not_detected` — the fact's patient-level claim directly includes that the molecular finding was not detected/absent;
   - `not_a_result` — the fact interprets a molecular finding or limitation rather than directly stating presence/absence.
4. `negative_consequence`: `true` when the fact says that a molecular finding has a negative, non-applicable, resistant, unsuitable, non-predictive, or otherwise limiting consequence. This includes statements such as a detected alteration being unsuitable for MRD or predicting resistance. It may coexist with `polarity: not_detected` when a negative result is followed by a caution such as "does not exclude".

Examples:

- `TP53 was not detected, so TP53-associated adverse risk does not apply.` → molecular true; targets `[TP53]`; polarity `not_detected`; negative_consequence true.
- `NPM1 mutation confers favourable prognostic significance.` → molecular true; targets `[NPM1]`; polarity `not_a_result`; negative_consequence false.
- `DNMT3A R882H should not be used for MRD monitoring.` → molecular true; targets `[DNMT3A]`; polarity `not_a_result`; negative_consequence true.
- `Allogeneic transplantation should be considered early.` → molecular false; targets `[]`; polarity `not_a_result`; negative_consequence false.
- `FLT3 mutation predicts resistance to a specified therapy.` → molecular true; targets `[FLT3]`; polarity `not_a_result`; negative_consequence true.

Consistency rules:

- `molecular: true` requires at least one target.
- `molecular: false` requires `targets: []`, `polarity: not_a_result`, and `negative_consequence: false`.
- Do not classify a general management recommendation as molecular merely because molecular information contributed to the upstream reasoning.
- Do not convert an interpretive fact into `detected` merely because it refers to a mutation known to be present; `detected` is reserved for a direct positive-result statement.
- Do not rewrite, merge, split, add, or delete facts.
- Use `reason` only as context for understanding the supplied fact.
- Do not make citation decisions and do not search for new evidence.
