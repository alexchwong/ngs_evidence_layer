# Full reporting-rule re-analysis

## Task

The diagnostic CMC changed. Re-answer R0-R5 from scratch using the evidence supplied for this pass. The refined CMC is fixed; do not change, re-route, propose, or emit another CMC.

{{REPORTING_RULE_POLICY}}

## YAML encoding

The shared policy above uses `REPORT:` and `OMIT:` terminology. In `report-draft-remainder.yaml`, encode `REPORT:` as `omit: false` and `OMIT:` as `omit: true`. Do not add a separate classification field. Every rule must still contain at least one atomic statement.

## Evidence boundary

Treat `downstream_evidence.md` as the complete literature-evidence boundary for this pass, including its recalled diagnosis evidence. Use only runtime card tags exposed there.

## Citation contract

Apply `workflows/categorical_v1/prompts/citation_rules.md`. Citation provenance is statement-level in YAML; do not collapse multiple independently supported assertions into one citation union.

{{CANONICAL_RULES}}
