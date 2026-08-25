# Terraced v6

Terraced v6 is the simplified prototype derived from v5. It deliberately removes downstream semantic repair and model-driven summarisation.

## Quick start

### Default `self` execution

`self` is the default session-model path. It uses the new additive native executor and the same shared proformas/contracts as staged v6:

```bash
python workflows/terraced_v6/self.py setup \
  --mode nel-validate-brief --case-id 1
```

For native self, setup creates a unique system temporary directory by default. Add `--project` (the CLI form of exact `->project`) to create it under `<repo-root>/temp/`, or use `--work-dir <path>` for an explicit directory. The existing staged `step.py` work-directory behaviour is unchanged.

Use the printed work directory with the sequence documented in `SKILL.md`:

```text
structure + WHO1 (one continuous model pass)
ICC
WHO2 (authoritative WHO)
PTBG (one pass, four existing proformas)
evidence resolution
evidence audit
conditional cropped evidence adjudication
final report synthesis with original case context
```

The self executor never calls an LLM. It prints bounded file inputs/contracts/output paths for the current session model to read and write directly. There is no routine syntax-repair or report-preservation model pass.

### Existing staged providers

The existing `step.py` engine remains unchanged for non-self pipelines:

```bash
python workflows/terraced_v6/step.py pipelines
python workflows/terraced_v6/step.py pipeline-check --pipeline lmstudio
python workflows/terraced_v6/step.py setup --mode nel-validate-brief --case-id 1 --pipeline lmstudio
python workflows/terraced_v6/step.py run --work-dir <printed-work-dir>
```

Its existing `self` pipeline remains available as the legacy staged/handoff implementation, but `SKILL.md` routes normal session-model execution through `self.py`.

## Architecture

The clinical contracts/proformas under `prompts/`, `stages/`, and `schemas/` are shared by both execution engines. Only execution grouping differs.

### Native self path

1. In one continuous WHO1 reasoning pass, structure `case.md`, let Python assign canonical `vNN` identities/retrieve WHO evidence, then complete the existing WHO5 proforma.
2. Run isolated ICC. WHO1 may influence deterministic CMC retrieval but its diagnosis is not exposed to ICC.
3. Run isolated WHO2 with the existing WHO5 contract and any CMC-triggered WHO card redraw. WHO2 is authoritative downstream.
4. Complete prognosis, treatment, MRD and germline in one model pass, still writing each existing proforma independently.
5. Deterministically construct candidate evidence pools, then run one evidence-resolution pass. No reason has assigned cards before this stage.
6. Run one independent evidence audit. Selected cards are audited; zero-card decisions receive a full candidate check.
7. Python accepts agreements and crops only disagreements. A short adjudication pass runs only when the resolver and auditor disagree.
8. Python applies evidence/no-support policy and builds deterministic report blocks.
9. One final synthesis pass receives the original case context plus audited blocks. Python then renders citations, evidence provenance, `dissent.md`, final JSON and validation packages.

### Existing staged path

`step.py` retains its previous WHO/ICC/second-diagnosis, per-domain PTBG, retrying evidence, report-write and preservation topology for non-self providers. No staged-path dependency is changed by the native-self implementation.

## Minimal proformas

- Diagnosis: WHO5, ICC, independent second diagnosis.
- Prognosis: favorable, adverse, neutral, uncertain, prognostic score.
- Treatment: drug target, drug sensitive, drug resistant, no drug implication.
- MRD: marker, not marker.
- Germline: support, against, uncertain; every conclusion must integrate the NGS result with supplied clinical context.

Variant IDs (`v01`, `v02`, ...) link owner reasoning to the structured variant registry, and are the only variant identifiers any model sees.

Owner models return one row per variant (`variant`, `bucket`, `reason`), filling in a pre-supplied skeleton. Rows sharing one proposition are merged deterministically afterwards and recorded in `logs/transforms.yaml`; the stored proforma keeps the familiar bucket-list shape.

## Card rendering

All evidence cards shown to models use one shared renderer and 12-character runtime card tags. `rendering.cards` in `settings.json` may be `compact` (default) or `verbose`. Compact mode groups cards by source hint, category, then diseases and emits one card per line as `[card:<tag>] Interpretation (evidence_tier: ...)`; gene metadata and canonical corpus card IDs are not repeated model-side.

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
- `report-final.json` — final blocks, report, risks, and usage.
- `ngs-report-debug.zip` — native-self debug bundle of run artifacts (ZIP outputs excluded to avoid recursive packaging).
- `nel-validation*.zip` — external-marking bundle in validation modes.
- `dissent.md` — semantic dissent history, only when dissent exists.
- `intermediates/*diagnosis*` and `*_state/proforma.yaml` — owner-model conclusions.
- `intermediates/report_blocks/report-blocks.yaml` — deterministic composition contract sent to the final writer.
- `logs/workflow.log` — run trace.
- `logs/transforms.yaml` — every deterministic change made to an accepted model artifact.

## Failure policy

Every failed semantic evidence audit is retained in `dissent.md`, even if a later card passes. PTBG propositions are suppressed when semantic evidence resolution is exhausted. For primary WHO5/ICC diagnoses, unsupported molecular/cytogenetic refinements fall back to explicitly supplied morphology; unsupported inferred morphology remains unresolved and is omitted. The final prose writer never gets permission to change clinical conclusions.
