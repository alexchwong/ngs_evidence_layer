# ICC molecular/cytogenetic diagnosis update

Accept the supplied morphologic diagnosis as the starting diagnosis. Do not re-establish it from morphology, cytopenias, or blast count.

Using only the supplied ICC authority cards, decide whether the NGS findings and supplied cytogenetics alter, refine, supersede, or leave unchanged the starting diagnosis under ICC.

The WHO5 diagnosis is supplied only as context. Do not alter it and do not write a separate WHO5/ICC comparison.

Rules:
- Return one ICC diagnosis only.
- `variants` contains only variant IDs that materially contribute to the ICC diagnosis update; it may be empty.
- Use deterministic finite-gene-set membership supplied by core when present.
- Do not claim an unlisted variant satisfies a closed molecular criterion.
- `reason` is one concise patient-level proposition about the molecular/cytogenetic effect on diagnosis. Do not relitigate morphology.

Return YAML only:
```yaml
diagnosis: "<ICC diagnosis>"
variants: [v01]
reason: "<one concise reason>"
```
