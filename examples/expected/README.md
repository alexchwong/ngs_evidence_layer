# Expected demo behaviour

Each numbered file in this directory corresponds to the same-numbered clinical
case in `examples/cases/`.

These files contain human-reviewed expectations and case commentary for
`nel-demo`. They are comparison material, not clinical case input and not a gold
standard for exact report wording.

`nel-demo example <N>` must run the complete `ngs-report` workflow without reading
the matching expected file. Step 7 begins only after Step 6B has produced
`report-final.md`. Step 7 renders `report-final.md` for every report-producing mode;
for `nel-demo`, it is also the first point at which the expected file may be read
and displayed beside the case and generated report.

Expected files should describe behaviour that matters for the example, such as:
- diagnostic-category refinement or preservation;
- evidence-bounded uncertainty;
- retrieval or suppression behaviour;
- handling of genes not represented in the corpus;
- report conclusions that should or should not follow from available evidence.

Do not store patient facts only in this directory. Any fact required by the
workflow belongs in the corresponding file under `examples/cases/`.
