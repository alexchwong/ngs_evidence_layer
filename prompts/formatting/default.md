# Default NGS report formatting

Use `report-draft.md` as the sole source of content.

<!--
Customise report length, content emphasis, section ordering, and omission rules below.
Source constraints and referencing rules should normally be left unchanged.
-->

## Source and output constraints

- Do not add facts that are not present in `report-draft.md`.
- Do not add interpretations that are not present in `report-draft.md`.
- Do not add recommendations that are not present in `report-draft.md`.
- Do not add citations that are not present in `report-draft.md`.
- Do not mention reporting rules.
- Do not mention the evidence block.
- Do not mention the drafting process.

## General formatting

- Write a concise final clinical NGS report.
- Maximum 200 words, excluding citations.
- Use full sentences.
- Include only the most clinically important conclusions from `report-draft.md`.
- Preserve clinically important qualifications and uncertainty.

## Variant summary

- The first sentence MUST summarise the detected NGS variants.
- List genes in alphabetical order.
- Give variant type and VAF in brackets following each gene (e.g. missense, 30%).
- Use a recognised hotspot name when the variant type or hotspot is clinically important (e.g. JAK2 V617F, FLT3-ITD or TKD, NPM1 type A).
- Otherwise, describe the protein consequence (missense, frameshift-truncating, splice site, stop-codon truncating, etc).

## Diagnosis

- Following the variant summary, declare the WHO diagnosis.
- Following the WHO diagnosis, state the ICC diagnosis if and only if it is materially different to the WHO diagnosis.
- Prioritise information that changes diagnosis.

## Prognosis

- Prioritise information that changes prognosis.
- For each variant detected on NGS, state their material contribution to the relevant prognostic scoring (adverse, favourable, or neutral).

## Treatment

- Omit this section if there are no NGS (or other molecular results given in the case) that changes treatment.
- Prioritise information that changes treatment.
- For NGS variants that alters treatment-specific outcomes, first assess whether the patient would otherwise be eligible for this treatment. If not, then do not report the corresponding treatment-specific effects. 

## Biomarkers and MRD

- When a gene is a biomarker, specify the exact variant; a hotspot name suffices if one exists.
- Prioritise information that changes MRD interpretation.

## Germline predisposition

- Prioritise information that changes assessment of possible germline predisposition.

## Handling negative statements

- Omit statements that only say what a finding does not imply or should not be used for.
- Retain negative test results only when they materially affect diagnosis, classification, prognosis, or response assessment.

## Compression

- When multiple genes have the same clinical implication, group them in one statement rather than describing each separately.

## Referencing

`report-draft.md` contains exact card-ID markers attached to its statements.

- For every retained statement, copy all associated `[card:<card-id>]` markers
  verbatim and keep them attached to the facts they support.
- When combining retained statements, copy all of their supporting card-ID markers
  verbatim and adjacently.
- Retain `(no citation required)` for each retained sentence that has that marker.
- Do not add, reconstruct, edit, replace, parse, or renumber citation markers.
- Do not write numeric citations or a `References` section; deterministic Step 6C
  performs citation replacement and bibliography rendering.
