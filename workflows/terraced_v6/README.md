# Terraced v6

## Legacy status

Terraced-v6 is retained as a runnable legacy/reproducibility workflow. It uses `workflows/terraced_v6/settings.json.template` and `workflows/terraced_v6/pipelines/` as its defaults. Root `config/settings.json.template` and `config/pipelines/` belong to canonical `proforma-v1` and are not terraced-v6 configuration.


Terraced v6 is the simplified prototype derived from v5. It deliberately removes downstream semantic repair and model-driven summarisation.

## Quick start

### Default `self` execution

`self` is the default session-model path. It uses the new additive native executor and the same shared proformas/contracts as staged v6:

```bash
python workflows/terraced_v6/self.py setup \
  --mode nel-validate-dublin --case-id 1

python nel.py setup --legacy \
  --mode nel-validate-dublin --case-id 1 --pipeline self --run-id legacy-dublin-1
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

The existing `step.py` engine remains available for non-self pipelines:

```bash
python workflows/terraced_v6/step.py pipelines
python workflows/terraced_v6/step.py pipeline-check --pipeline lmstudio
python workflows/terraced_v6/step.py setup --mode nel-validate-dublin --case-id 1 --pipeline lmstudio
python workflows/terraced_v6/step.py run --work-dir <printed-work-dir>
```

Its existing `self` pipeline remains available as the legacy staged/handoff implementation, but `SKILL.md` routes normal session-model execution through `self.py`.

## Architecture

The clinical contracts/proformas under `prompts/`, `stages/`, and `schemas/` are shared by both execution engines. Only execution grouping differs.
Terraced-v6 keeps its legacy defaults entirely workflow-local in `settings.json.template` and `pipelines/*.yaml`. Direct legacy runs use those files (or a workflow-local `settings.json` if present). Root `nel.py` does not use terraced defaults for new runs; it binds terraced only when resuming a frozen root run whose manifest records `workflow: terraced-v6`.

### Native self path

1. In one continuous WHO1 reasoning pass, structure `case.md`, let Python assign canonical `vNN` identities/retrieve WHO evidence, then complete the existing WHO5 proforma.
2. Run isolated ICC. WHO1 may influence deterministic CMC retrieval but its diagnosis is not exposed to ICC.
3. Run isolated WHO2 with the existing WHO5 contract and any CMC-triggered WHO card redraw. WHO2 is authoritative downstream.
4. Complete prognosis, treatment, MRD and germline in one model pass, still writing each existing proforma independently.
5. Deterministically construct candidate evidence pools, then run one evidence-resolution pass. No reason has assigned cards before this stage.
6. Run one independent evidence audit. Selected cards are audited; zero-card decisions receive a full candidate check.
7. Python accepts agreements and crops only disagreements. A short adjudication pass runs only when the resolver and auditor disagree.
8. Python applies evidence/no-support policy, deterministically aggregates evidence-resolved prognosis findings into report-sized clinical propositions, and builds deterministic report blocks.
9. One final synthesis pass receives the original case context plus audited blocks. Python then renders citations, evidence provenance, `dissent.md`, final JSON and validation packages.

### Existing staged path

`step.py` retains its previous WHO/ICC/second-diagnosis, per-domain PTBG, retrying evidence, report-write and preservation topology for non-self providers. Both staged and native-self execution now normalize structured NGS state the same way: `structure_case` identifies detected variants and whether the result is complete, then Python materializes `ngs_no_variants_detected` from the configured panel scope for downstream clinical reasoning.

## Minimal proformas

- Diagnosis: WHO5, ICC, independent second diagnosis.
- Prognosis: authoritative disease, zero/one/multiple disease-applicable prognostic frameworks, optional framework tier, and per-variant framework/other-evidence effects.
- Treatment: disease-scoped drug target, drug sensitive, drug resistant, no drug implication.
- MRD: disease-scoped marker, not marker.
- Germline: support, against, uncertain; every conclusion must integrate the NGS result with supplied clinical context.

Variant IDs (`v01`, `v02`, ...) link owner reasoning to the structured variant registry, and are the only variant identifiers any model sees.

For a complete NGS result, `case.json` also contains `ngs_no_variants_detected`: every configured panel gene without a detected NGS variant, generated deterministically rather than copied by the model. If the case explicitly says the NGS result is partial, selected, limited, abbreviated, pending, or otherwise incomplete, the list is empty. These negatives apply only to the variant classes defined by `config/ngs-panel-scope.md`.

Owner models use variant-centric skeletons. Prognosis returns `prognostic_frameworks` plus one row per variant with framework-specific effects and an independent same-disease evidence effect. Treatment uses `treatment_category`; MRD uses `mrd_status`; germline retains its existing `bucket`. Python injects/overwrites canonical `gene` and the authoritative disease where applicable, then projects the accepted owner output into the stable bucketed internal shape used downstream. Rows sharing one proposition are merged deterministically afterwards and recorded in `logs/transforms.yaml`.

## Card rendering

All evidence cards shown to models use one shared renderer and 12-character runtime card tags. `rendering.cards` in the workflow-local terraced settings may be `compact` (default) or `verbose`. Compact mode groups cards by source hint, category, then diseases and emits one card per line as `[card:<tag>] Interpretation (evidence_tier: ...)`; gene metadata and canonical corpus card IDs are not repeated model-side.

WHO5 and ICC diagnostic pools are configured independently under `diagnosis.who5` and `diagnosis.icc`. Each has an `included_publication_keys` allowlist and an `excluded_publication_keys` denylist. An empty inclusion list includes all retrieved publications. Python then removes excluded publications, so exclusion takes precedence when a publication is present in both lists. The resulting pool is shared by diagnostic prompt rendering, finite-set context, and downstream evidence resolution.

Downstream PTBG retrieval is scoped to the authoritative WHO5 `schema_disease`; it does not expand through disease-vocabulary `retrieval_related` links. Prognosis receives all prognosis cards explicitly applicable to the exact disease so the owner can identify disease-level frameworks even when no framework gene is mutated; Step 5 then crops variant-specific prognosis propositions back to the exact variant gene. Treatment and MRD require exact disease plus a case-gene match. Germline requires a case-gene match and accepts either disease-neutral cards or cards explicitly tagged to the exact authoritative disease. Explicitly multi-disease cards remain valid because exact membership is tested against the card's own `diseases` list. The evidence-audit boundary deterministically re-checks disease/domain applicability before semantic audit.

Evidence matching remains batched, but each evidence item is rendered beside only its own deterministic candidate-card set. WHO5 and ICC pools therefore stay separated at model presentation rather than being recombined into one mixed catalog.

After evidence resolution, `prognosis_report.py` performs one deterministic report-only aggregation pass. Same-framework/same-direction variant findings are grouped to gene-level report scope; multiple variants in one gene collapse to that gene. Independent same-disease prognosis remains separate. An `other_evidence` proposition is suppressed as a redundant framework restatement only when the same gene/direction is already framework-supported and all of that proposition's accepted cards are already used by the same-direction framework effect. The trace is written to `intermediates/prognosis_report_aggregation/aggregation.yaml`; the upstream prognosis proforma and evidence-resolution artifacts remain variant-centric and unchanged.

## Reportability

For a new legacy run, copy `workflows/terraced_v6/settings.json.template` to the gitignored workflow-local `workflows/terraced_v6/settings.json` if custom settings are needed. Defaults suppress routine negative/uncertain prose while retaining it in owner proformas:

- prognosis `no_prognostic_evidence`: false
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
- `intermediates/prognosis_report_aggregation/aggregation.yaml` — deterministic post-evidence prognosis grouping/suppression trace.
- `intermediates/report_blocks/report-blocks.yaml` — deterministic composition contract sent to the final writer.
- `logs/workflow.log` — run trace.
- `logs/model-usage.json` — provider-call timing, token usage, and provider-reported cost for non-self pipelines.
- `logs/transforms.yaml` — every deterministic change made to an accepted model artifact.

For OpenRouter, run cost is the sum of the cost returned for each physical provider call, including retries and syntax repairs. NEL does not maintain a pricing table or estimate missing monetary usage.

## Failure policy

Every failed semantic evidence audit is retained in `dissent.md`, even if a later card passes. PTBG propositions are suppressed when semantic evidence resolution is exhausted. For primary WHO5/ICC diagnoses, unsupported molecular/cytogenetic refinements fall back to explicitly supplied morphology; unsupported inferred morphology remains unresolved and is omitted. The final prose writer never gets permission to change clinical conclusions.
