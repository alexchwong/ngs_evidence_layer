# NGS panel scope

This file defines the gene-level scope of the laboratory NGS panel used by this workflow.
It intentionally does not encode transcript, exon, or amplicon numbers.

## Genes assessed

- `ABL1`
- `ANKRD26`
- `ASXL1`
- `BCOR`
- `BCORL1`
- `BRAF`
- `CALR`
- `CBL`
- `CEBPA`
- `CSF3R`
- `DDX41`
- `DNMT3A`
- `ETNK1`
- `ETV6`
- `EZH2`
- `FLT3`
- `GATA1`
- `GATA2`
- `HRAS`
- `IDH1`
- `IDH2`
- `IKZF1`
- `JAK2`
- `KIT`
- `KRAS`
- `MPL`
- `MYD88`
- `NF1`
- `NPM1`
- `NRAS`
- `PHF6`
- `PPM1D`
- `PRPF8`
- `PTPN11`
- `RAD21`
- `RB1`
- `RUNX1`
- `SETBP1`
- `SF3B1`
- `SH2B3`
- `SMC1A`
- `SMC3`
- `SRSF2`
- `STAG2`
- `STAT3`
- `STAT5B`
- `TET2`
- `TP53`
- `U2AF1`
- `UBA1`
- `WT1`
- `ZRSR2`

## Negative-result semantics

When the patient NGS result is explicitly complete, a listed panel gene that is absent from the detected-variant list is interpreted as **no SNV, short insertion/deletion, or short-range complex variant detected in that gene within the validated assay scope**.

Use this negative result when applying diagnostic, prognostic, biomarker, treatment, germline, and other reporting rules. Do not treat the gene as unresolved merely because it is not individually listed in the patient result.

This inference is limited to the assay scope. It does not establish whole-gene biological wild type and does not exclude copy-number changes, rearrangements, structural variants, or other variant classes unless the patient result or another supplied test explicitly assesses them.

If the patient NGS result is described as partial, selected, limited, abbreviated, pending, or otherwise incomplete, do not infer a negative result for an unlisted panel gene.
