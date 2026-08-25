# Downstream reporting rules

## Task

The diagnostic pass is complete. Answer R2-R5 only. Use the established diagnostic context injected below; do not re-answer R0-R1 or change the refined CMC.

{{DIAGNOSIS_CONTEXT}}

{{REPORTING_RULE_POLICY}}

## YAML encoding

The shared policy above uses `REPORT:` and `OMIT:` terminology. In `report-draft-remainder.yaml`, encode `REPORT:` as `omit: false` and `OMIT:` as `omit: true`. Do not add a separate classification field. Every rule must still contain at least one atomic statement.

## Evidence boundary

Treat `downstream_evidence.md` as the complete literature-evidence boundary for this pass. Use the injected `report-summary-dx.yaml` only as prior patient-level diagnostic context, never as a source of new runtime card tags. Use only runtime card tags exposed in `downstream_evidence.md`.

## Citation contract

Apply `workflows/categorical_v1/prompts/citation_rules.md`. Citation provenance is statement-level in YAML; do not collapse multiple independently supported assertions into one citation union.

{{CANONICAL_RULES}}
