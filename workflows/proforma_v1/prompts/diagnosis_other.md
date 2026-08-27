# Independent concurrent diagnosis

Consider only whether the NGS findings or supplied cytogenetics support a genuinely independent concurrent diagnosis in addition to the primary WHO5/ICC disease.

Do not return:
- a refinement or more specific subtype of either primary diagnosis;
- an alternative framework label for the same disease;
- a diagnosis that supersedes either primary diagnosis;
- a restatement of a molecular criterion already used by WHO5 or ICC.

- `ngs_no_variants_detected` means no SNV, short insertion/deletion, or short-range complex variant was detected in those genes within validated NGS assay scope; do not extend that negative result to copy-number changes, rearrangements, structural variants, or other unassayed variant classes.

If none is supported, return null without explanation.

Return YAML only:
```yaml
diagnosis: null
variants: []
reason: null
```

Or, when an independent concurrent diagnosis is supported:
```yaml
diagnosis: "<independent concurrent diagnosis>"
variants: [v01]
reason: "<one concise reason>"
```
