# `reasoning.yaml`

`reasoning.yaml` is the experimental atomic-reasoning proforma-v1 workflow. `default.yaml` remains the shipped workflow and is intentionally not modified by this implementation.

## Diagnostic architecture

WHO5, ICC and second/concurrent diagnosis are independent owners. Their literature rules are evidence-audited separately from patient applicability, then Python evaluates shallow `all_of` / `any_of` logic. Owner-proposed evidence assignments are accepted only inside frozen authority envelopes; missing assignments use rescue-only matching. Evidence adjudication is a separate independent pass. Failed owners receive one complete plain-English feedback bundle and one bounded redo before deterministic fallback/suppression.

## PTBG architecture

Prognosis, treatment, biomarker/MRD and germline remain four logical owners. Each emits atomic propositions containing literature rules, optional derived patient states, applications and deterministic conclusion logic.

- Prognosis explicitly separates framework applicability, framework rules, patient state, rule application and conclusion.
- Treatment and biomarker can use exact deterministic applicability for literal one-fact matches and semantic audit only when needed.
- Germline preserves a factor worksheet whose entries reference independently auditable patient applications; no hidden numeric score is used.
- Owners may nominate evidence cards from their frozen domain envelope. A matcher runs only for missing assignments.
- Evidence audit is rule/card fidelity only. Patient applicability is audited later.
- Direct applicability is evaluated in Python only when an exact supplied fact/value comparison is declared. Composite applicability goes to the reasoning auditor.
- Every reportable proposition is deterministically classified as kept, revised, dropped, unresolved or not reportable. Failed domain owners receive one bounded redo without rerunning unrelated owners.

## Self execution

Native `self` is the frontier-model path and deliberately uses fewer physical passes than provider execution while preserving logical audit boundaries.

Routine target:

1. structure + WHO
2. ICC
3. second diagnosis
4. diagnostic review
5. all four PTBG owners in one grouped handoff
6. PTBG evidence/reasoning review
7. report + user-facing dissent summary in one grouped handoff

Evidence adjudication and owner redo always break into separate conditional passes. An owner is never combined with the independent audit/adjudication of its own output.

## Decision provenance and `dissent.md`

After PTBG review, `decision-ledger.yaml` records every diagnostic/PTBG decision and reviewed derived state, the facts considered, evidence rules/cards, terminal disposition and reason. `dissent.md` is then rendered deterministically from that ledger and always includes:

- outcome counts;
- facts considered;
- considered-and-kept/revised decisions;
- dropped decisions;
- unresolved decisions;
- non-reportable decisions;
- evidence rules and accepted cards for each decision.

A separate `dissent_summary` model role may add a short plain-English overview. It cannot change ledger dispositions. Invalid or unavailable summary output is ignored and the deterministic `dissent.md` remains complete, so presentation failure never blocks the clinical report.

Select explicitly:

```bash
python workflows/proforma_v1/step.py workflow-check --workflow workflow/reasoning.yaml
python workflows/proforma_v1/step.py setup --mode nel-demo --example 1 --pipeline self --workflow workflow/reasoning.yaml
```

Omitting `--workflow` continues to select `workflow/default.yaml`.
