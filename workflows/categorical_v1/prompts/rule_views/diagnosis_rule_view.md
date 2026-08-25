# Diagnosis-pass reporting rules

## Task

Answer R0-R1 only. Produce self-contained patient-level conclusions suitable for later report synthesis. The deterministic YAML template separately contains the refined CMC routing field; that field is not report content.

{{REPORTING_RULE_POLICY}}

## YAML encoding

The shared policy above uses `REPORT:` and `OMIT:` terminology. In `report-draft-dx.yaml`, encode `REPORT:` as `omit: false` and `OMIT:` as `omit: true`. Do not add a separate classification field. Every rule must still contain at least one atomic statement.

## Evidence boundary

Treat `diagnostic_evidence.md` as the complete literature-evidence boundary for this pass. Use only runtime card tags exposed there.

## Citation contract

Apply `workflows/categorical_v1/prompts/citation_rules.md`. Citation provenance is statement-level in YAML; do not collapse multiple independently supported assertions into one citation union.

{{CANONICAL_RULES}}
