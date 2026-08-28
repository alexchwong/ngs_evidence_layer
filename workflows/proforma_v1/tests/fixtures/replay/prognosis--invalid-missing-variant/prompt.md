# Prognosis

Using only the supplied case, authoritative diagnosis, and prognosis cards, assess prognosis in the authoritative disease context.

First identify the prognostic framework or frameworks that genuinely apply to the authoritative disease. Framework selection is a clinical model decision: zero, one, or multiple frameworks may be returned. Do not infer or change the disease from candidate cards, and do not select a framework merely because a card from another disease mentions a familiar gene or framework.

For every supplied variant, assess two independent evidence channels:
- `framework_effects`: effects explicitly defined by one of the named prognostic frameworks. A variant may have one effect per named framework. Use an empty list when it is not classified by any named framework.
- `other_evidence_effect`: prognosis supported by other evidence explicitly applicable to the same disease, whether or not the gene belongs to the named framework(s).

Allowed directions are `favorable`, `adverse`, and `neutral`. Use `no_evidence` for `other_evidence_effect` when there is no qualifying same-disease prognostic evidence.

A variant may appear in both a framework effect and other evidence when both apply. Treat these as independent evidence channels: preserve source-specific prognostic directions even when they differ, provided each direction is supported by its own applicable source.

For each framework, `tier` is optional. Populate it only when the framework tier can be assigned entirely from the supplied genetic/cytogenetic findings. Otherwise use `null`. The framework `reason` must support framework applicability and, when `tier` is populated, the tier assignment as well. Do not calculate combined clinical/molecular scores merely because the framework is relevant, and do not state that a tier or score is "not calculable".

`ngs_no_variants_detected` means no SNV, short insertion/deletion, or short-range complex variant was detected in those genes within validated NGS assay scope; do not extend that negative result to copy-number changes, rearrangements, structural variants, or other unassayed variant classes.

Keep every reason concise, report-ready, and faithful to the supplied evidence.
Evidence assignment:
- For every reportable proposition you create, also return `evidence_card_tags` using only exact card IDs supplied to this owner step.
- Use an empty list when none of the supplied cards genuinely supports that proposition. Do not copy a merely related card.
- A card tag outside the supplied owner envelope is invalid and the complete owner artifact will be returned for repair.
