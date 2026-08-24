# Terraced v6

Terraced v6 is the simplified prototype derived from v5. It deliberately removes downstream semantic repair and model-driven summarisation.

## Quick start

List available pipelines:

```bash
python workflows/terraced_v6/step.py pipelines
```

Validate/inspect the selected pipeline:

```bash
python workflows/terraced_v6/step.py pipeline-check --pipeline self
```

Set up validation brief 1:

```bash
python workflows/terraced_v6/step.py setup \
  --mode nel-validate-brief \
  --case-id 1 \
  --pipeline self
```

Check one stage's validator against a candidate artifact, with no model call:

```bash
python workflows/terraced_v6/step.py stages
python workflows/terraced_v6/step.py check-stage --stage prognosis --file candidate.yaml
python workflows/terraced_v6/step.py show-prompt --stage prognosis
```

Run or resume the run created by the immediately preceding `setup`:

```bash
python workflows/terraced_v6/step.py run
```

As in terraced v5, bare `run` selects the most recently created directory under `workflows/terraced_v6/runs/`. Use `--work-dir <run-directory>` only when you intentionally want a different existing run.

With `self`, each required model call returns `HANDOFF`, `PROMPT`, and `OUTPUT`; place the requested model response at `OUTPUT` and run the same command again. `lmstudio` and `openrouter` call their configured OpenAI-compatible endpoints directly.

## Architecture

1. Structure `case.md` and preserve detailed variants.
2. Deterministically initialise/filter the evidence corpus.
3. WHO5 and ICC each decide whether NGS/cytogenetics alter the supplied morphologic diagnosis; an independent concurrent diagnosis is considered separately.
4. Prognosis, treatment, MRD, and germline each produce one compact owner proforma.
5. Reportable owner propositions undergo one evidence match and one evidence audit.
6. `settings.json` deterministically filters reportability.
7. Python assembles deterministic report blocks.
8. One model call writes the prose.
9. One preservation-only audit checks the prose. Failed blocks fall back deterministically rather than entering a semantic rewrite loop.

No statement-generation/audit stage, summary planner, fragmentation repair, or paraphrase regeneration exists in v6.

## Minimal proformas

- Diagnosis: WHO5, ICC, independent second diagnosis.
- Prognosis: favorable, adverse, neutral, uncertain, prognostic score.
- Treatment: drug target, drug sensitive, drug resistant, no drug implication.
- MRD: marker, not marker.
- Germline: support, against, uncertain; every conclusion must integrate the NGS result with supplied clinical context.

Variant IDs (`v01`, `v02`, ...) link owner reasoning to the structured variant registry, and are the only variant identifiers any model sees.

Owner models return one row per variant (`variant`, `bucket`, `reason`), filling in a pre-supplied skeleton. Rows sharing one proposition are merged deterministically afterwards and recorded in `logs/transforms.yaml`; the stored proforma keeps the familiar bucket-list shape.

## Reportability

Edit `settings.json` (copied from `settings.json.template` when desired). Defaults suppress routine negative/uncertain prose while retaining it in owner proformas:

- prognosis `uncertain`: false
- treatment `no_drug_implication`: false
- MRD `not_mrd_marker`: false
- germline `germline_against`: false
- germline `germline_uncertain`: false

## Outputs

Pay attention to:

- `report-final.md` — final clinical report.
- `dissent.md` — semantic dissent history, if any.
- `report-final.json` — final blocks, report, risks, and usage.
- `intermediates/*diagnosis*` and `*_state/proforma.yaml` — owner-model conclusions.
- `intermediates/report_blocks/report-blocks.yaml` — deterministic composition contract sent to the final writer.
- `logs/workflow.log` — run trace.
- `logs/transforms.yaml` — every deterministic change made to an accepted model artifact.

## Failure policy

Primary WHO5/ICC propositions fail closed if evidence support cannot be established. Unsupported optional PTBG propositions are suppressed and recorded in `dissent.md`. The final prose writer never gets permission to change clinical conclusions.
