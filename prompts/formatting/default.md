# Default NGS report formatting

Use `report-draft.md` as the sole source of content.

Write a concise final clinical NGS report.

- Maximum 200 words, excluding citations.
- Use full sentences.
- Include only the most clinically important conclusions from `report-draft.md`.
- The first sentence MUST be a summary of what NGS variants were detected. It must adhere strictly to the following rules:
  - Genes in alphabetical order.
  - Variant type and VAF in brackets following each gene (e.g. missense, 30%)
  - If a variant type is important or hotspot (e.g. JAK2 V617F, FLT3-ITD or TKD, NPM1 type A), use the hotspot name for clarity.
  - Otherwise, describe protein consequence (missense, frameshift-truncating, splice site, stop-codon truncating, etc).
- Following the statement about NGS variants detect, declare the WHO diagnosis.
- Following the WHO diagnosis, state the ICC diagnosis if and only if it is materially different to the WHO diagnosis
- When a gene is a biomarker, specify exact variant (hotspot name suffices if it exists)
- Prioritise information that changes diagnosis, prognosis, management, MRD interpretation, or assessment of possible germline predisposition.
- Omit statements that only say what a finding does not imply or should not be used for.
- Retain negative test results only when they materially affect diagnosis, classification, prognosis, or response assessment.
- When multiple genes have the same clinical implication, group them in one statement rather than describing each separately.
- Preserve clinically important qualifications and uncertainty.
- Preserve the citations supporting each retained statement.
- Do not add facts, interpretations, recommendations, or citations that are not present in `report-draft.md`.
- Do not mention reporting rules, the evidence block, or the drafting process.

## Referencing

`report-draft.md` already contains deterministically generated Vancouver-style
square-bracket citations and a matching numbered `References` section.

- preserve every square-bracket citation attached to a retained statement
- copy each corresponding reference entry exactly as supplied
- include only references supporting statements retained in the final report
- do not add, reconstruct, edit, or renumber citations or reference entries
- the References section is excluded from the word limit