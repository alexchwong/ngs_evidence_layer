# Default diagnosis-first NGS report formatting

## General formatting

- Produce a concise clinical NGS summary with a maximum of 200 report-prose words.
- Use full sentences and include only the most clinically important retained conclusions from `report-draft.yaml`.
- Preserve clinically important qualifications and uncertainty.
- Do not weaken statement-level citation provenance to satisfy the word limit.

## Detected variants

- The first report sentence MUST summarise the detected NGS variants.
- List genes in alphabetical order.
- Give variant type and VAF in brackets following each gene.
- Use a recognised hotspot name when clinically important; otherwise describe the protein consequence.

## Diagnosis

- Following the variant summary, declare the WHO diagnosis.
- State the ICC diagnosis only if materially different.
- Prioritise information that changes diagnosis.

## Prognosis

- Prioritise the applicable disease-specific framework and risk assignment.
- State the material contribution of detected NGS variants to that framework.
- Group variants with the same effect when this preserves citation correctness.

## Treatment

- Omit treatment content when no supplied molecular finding materially changes treatment.
- Prioritise disease- and setting-specific actionable implications.

## MRD

- Report only clinically material molecular MRD implications.
- Specify the exact variant when relevant.

## Germline predisposition

- Report only content that materially changes assessment of possible germline predisposition.

## Compression

- Group facts when clinically natural, but only merge statements when the resulting citation field can correctly represent the evidence supporting all retained facts.
