# Default NGS report formatting

This file controls report style and content prioritisation only. Mandatory source-integrity and citation-marker constraints are defined by the active reporting workflow and its workflow-local `citation_rules.md`.

<!--
Customise report length, content emphasis, section ordering, and omission rules below.
Do not duplicate detailed source-integrity or citation-marker mechanics here; those are enforced by
the reporting workflow for every formatting style.
-->

## General formatting

- Write a concise final clinical NGS report.
- Maximum 200 report-prose words. Runtime card IDs and workflow citation dispositions do not count toward this limit.
- Formatting, compression, and word-count instructions MUST NOT remove, alter, or separate citation markers from the sentence they support.
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


## Compression

- When multiple genes have the same clinical implication, group them in one statement rather than describing each separately.
