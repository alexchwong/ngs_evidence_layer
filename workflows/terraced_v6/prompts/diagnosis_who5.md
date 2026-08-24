# WHO5 molecular/cytogenetic diagnosis update

Accept the supplied morphologic diagnosis as the starting diagnosis. Do not re-establish the morphologic diagnosis from cytopenias, dysplasia, blast count, or other non-molecular features.

Using only the supplied WHO5 authority cards, decide whether the NGS findings and supplied cytogenetics alter, refine, supersede, or leave unchanged the starting diagnosis.

Rules:
- Return one WHO5 diagnosis only.
- Use one exact supplied `schema_disease` for deterministic routing.
- `variants` contains only variant IDs that materially contribute to the WHO5 diagnosis update; it may be empty.
- Use deterministic finite-gene-set membership supplied by core when present.
- Do not claim an unlisted variant satisfies a closed molecular criterion.
- `reason` is one concise patient-level proposition about the molecular/cytogenetic effect on diagnosis. Do not relitigate morphology.

Return YAML only:
```yaml
schema_disease: "<allowed schema disease>"
diagnosis: "<WHO5 diagnosis>"
variants: [v01]
reason: "<one concise reason>"
```
