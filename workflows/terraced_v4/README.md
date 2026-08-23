# Terraced v4 prototype

Terraced-v4 is a deliberately small prototype cloned conceptually from terraced-v3. It keeps v3 provider/model plumbing, case initialisation, deterministic WHO5→CMC routing, chronological model-step capture, and the plan→paraphrase summarisation pattern. The v3 scheduler/statement-ledger/evidence-pairing architecture is not used.

## Flow

1. Structure `case.md`; create stable patient variant registry `v01`, `v02`, ...
2. Diagnosis pass 1 from bootstrap CMC evidence.
3. Derive CMCs deterministically from WHO5 schema disease and redraw diagnostic cards.
4. Diagnosis pass 2: start from scratch when CMC changes; otherwise edit/reconsider pass 1. Pass 2 is authoritative.
5. One proforma pass each for prognosis, treatment, biomarker/MRD and germline. Every variant must be covered.
6. Match each reportable reason to the closest semantic evidence card, with at most three obvious-mismatch rematches. Subjective citation concerns are logged, not made gating.
7. Generate one reportable sentence per schema element.
8. Plan safe same-domain sentence combinations, then paraphrase each planned sentence.
9. Render citations deterministically from the evidence cards inherited through schema/sentence IDs.

## CLI

```bash
python workflows/terraced_v4/step.py pipelines
python workflows/terraced_v4/step.py pipeline-check --pipeline self
python workflows/terraced_v4/step.py setup --mode ngs-report --case-file case.md --pipeline self
python workflows/terraced_v4/step.py run --work-dir <run-dir>
```

Use `--pipeline lmstudio` or `--pipeline openrouter` as configured in `pipelines/`.

## Run directory

- `model_steps/`: chronological accepted model operations/prompts.
- `intermediates/`: machine-readable workflow state.
- `logs/workflow.log`: CLI/runtime log.
- `logs/risk_log.yaml`: non-gating evidence/summarisation risks and graceful degradations.
- `logs/errors/`: invalid/retried model artifacts.
- root: final deliverables only (`report-final.md`, `report-final.json`, and validation package where applicable), plus immutable workflow inputs/state created by common setup.

## Prototype limitations

Two diagnosis passes are intentionally fixed. If pass 2 changes the CMC again, the workflow logs that no third redraw occurred. Citation audit detects obvious mismatch and fidelity risk but does not claim to prove semantic entailment. Negative PTBG buckets are coverage/audit state and do not automatically become report sentences.
