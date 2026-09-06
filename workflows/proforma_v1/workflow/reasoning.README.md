# `reasoning.yaml`

`reasoning.yaml` is the experimental reasoning-first proforma-v1 workflow. Clinical models make clinical judgements; Python owns machine representation. `default.yaml` retains its existing execution graph and gains only embedded UI presentation metadata.

## Core boundary

For every clinical owner:

```text
clinical reasoning → Python normalization → evidence match → Python compile/validate
```

The reasoning model does **not** assign evidence cards and does not author the internal atomic graph. It uses source-facing case/variant IDs and a lightweight reasoning schema. Python deterministically creates internal IDs, resolves source/internal aliases, fills machine-only fields and compiles the strict internal graph.

Evidence matching is a separate bounded judgement. It receives immutable reasoning rules plus the tagged candidate-card envelope and may only assign supporting cards; it cannot modify the clinical conclusion or patient applicability reasoning.

## Diagnosis

WHO5, ICC and second/concurrent diagnosis are independent owners:

1. WHO reason → WHO evidence match
2. ICC reason → ICC evidence match
3. second-diagnosis reason → second evidence match
4. grouped diagnostic evidence audit
5. separate grouped diagnostic reasoning audit
6. Python evaluation/finalization

Evidence audit asks only whether assigned literature supports each rule. Reasoning audit separately asks whether evidence-audited rules have been applied correctly to the supplied patient facts and whether the clinical conclusion follows.

A rejected card assignment retries that owner's evidence-match step. An unsupported clinical proposition or patient-applicability/conclusion defect retries that owner's reasoning step. Machine/schema representation defects are Python/compiler defects and never consume a clinical-owner retry.

## PTBG

Prognosis, treatment, biomarker/MRD and germline use the same architecture independently:

```text
P reason → P evidence match
T reason → T evidence match
B reason → B evidence match
G reason → G evidence match
        ↓
grouped PTBG evidence audit
        ↓
grouped PTBG reasoning audit
        ↓
Python evaluation
```

There is no grouped PTBG-owner reasoning handoff. Each domain has one bounded judgement at a time.

## Native self

Native `self` follows the same logical and cognitive boundaries as provider execution. Reasoning, evidence matching, evidence auditing, evidence adjudication and reasoning auditing are separate frontier handoffs. Deterministic Python steps may run between them. The only retained grouping is downstream final presentation, where report writing and ledger-faithful dissent presentation do not combine different clinical judgement types.

## UI progress

Progress presentation is embedded in the workflow YAML under the clearly separate top-level `presentation.progress_phases` section. It is UI-only and cannot alter execution, dependencies, retries or routing.

The reasoning workflow exposes these meaningful phases before existing downstream report phases:

- Diagnosis — WHO
- Diagnosis — ICC
- Diagnosis — Second
- Diagnosis — Evidence audit
- Diagnosis — Reasoning audit
- Prognosis
- Treatment
- Biomarker
- Germline
- PTBG — Evidence audit
- PTBG — Reasoning audit

Internal normalize/compile/validation/retry steps remain inspectable in model activity and workflow traces without becoming progress-bar phases.

The former `default.progress.yaml` and `reasoning.progress.yaml` sidecars are obsolete; progress metadata now lives inside `default.yaml` and `reasoning.yaml`.

## Decision provenance and `dissent.md`

After PTBG review, `decision-ledger.yaml` records diagnostic/PTBG decisions, facts considered, accepted evidence, terminal disposition and reason. `dissent.md` remains deterministically rendered from that ledger. The optional dissent-summary model cannot change ledger dispositions.

Select explicitly:

```bash
python workflows/proforma_v1/step.py workflow-check --workflow workflow/reasoning.yaml
python workflows/proforma_v1/step.py setup --mode nel-demo --example 1 --pipeline self --workflow workflow/reasoning.yaml
```

Omitting `--workflow` continues to select `workflow/default.yaml`.
