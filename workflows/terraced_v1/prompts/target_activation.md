# Terraced-v1 target-activation context extraction

Extract only the explicit case-context signals needed to decide which molecular targets were already up for discussion before Step 6 reportability decisions are applied.

Do not decide whether any report fact should be retained or quarantined. Do not infer a diagnosis from morphology, phenotype, laboratory features, or general domain knowledge. A phenotype such as an IgM paraprotein does not itself activate MYD88 here unless the supplied case or diagnostic state explicitly raises a diagnosis that will later be linked to MYD88 by diagnosis-card retrieval.

Return only:

```yaml
direct_targets:
  - target: TP53
    bases: [explicitly_mentioned_in_stem]
stem_diagnoses:
  - schema_disease: APL
```

`direct_targets` may be empty. For each target use a canonical gene or named fusion/rearrangement target at gene/fusion level, not HGVS variant detail. Examples: `TP53`, `NPM1`, `BCR::ABL1`, `PML::RARA`, `FLT3`.

Use one or more of these closed `bases` values:

- `explicitly_mentioned_in_stem` — the molecular target is explicitly named in the clinical stem;
- `previously_detected` — a prior specimen/test in the clinical stem explicitly detected that target;
- `explicitly_requested_or_excluded` — the clinical stem explicitly asks to test, assess, exclude, confirm, or discuss that target.

A previously detected or explicitly requested target will normally also qualify as explicitly mentioned; include every applicable basis.

`stem_diagnoses` contains only diagnoses explicitly named or explicitly proposed/excluded in the clinical stem. Map them to exact supplied canonical `schema_disease` values. Do not infer an unspoken diagnosis from morphology or phenotype. The accepted diagnostic answer is supplied separately and is added deterministically downstream, so do not invent additional diagnoses merely because they seem clinically plausible.

Strict boundaries:

- extract context only from the supplied clinical stem/structured case/accepted diagnostic state;
- do not use the accepted report facts as evidence of activation;
- do not decide whether a target was detected in the final report fact set;
- do not retrieve evidence or use general medical knowledge to add target associations;
- do not add prose, reasons, reportability verdicts, or citations.
