# Terraced v4 prototype

Terraced-v4 is a deliberately small prototype cloned conceptually from terraced-v3. It keeps v3 provider/model plumbing, case initialisation, deterministic WHO5→CMC routing, authority-specific diagnosis evidence, chronological model-step capture, and ID-preserving report synthesis. The v3 scheduler/statement-ledger machinery is not used.

## Quick start

List shipped pipelines:

```bash
python workflows/terraced_v4/step.py pipelines
```

Validate a pipeline before running it:

```bash
python workflows/terraced_v4/step.py pipeline-check --pipeline self
```

Run validation brief case 1 with the self pipeline:

```bash
python workflows/terraced_v4/step.py setup \
  --mode nel-validate-brief \
  --case-id 1 \
  --pipeline self
```

Then continue the scripted run:

```bash
python workflows/terraced_v4/step.py run --work-dir <run-directory>
```

For `self`, the CLI emits model handoffs to be completed by the session model. LM Studio and OpenRouter pipelines call their configured OpenAI-compatible endpoints directly.

## Flow

1. Structure `case.md`; create stable patient variant registry `v01`, `v02`, ...
2. WHO5 pass 1 runs from bootstrap CMC evidence using **Khoury 2022 cards only**.
3. Derive CMCs deterministically from WHO5. If CMC changes, WHO5 pass 2 starts from scratch using cumulative old+new CMC evidence, again Khoury-only. If CMC does not change, pass 1 is authoritative and there is no WHO5 pass 2.
4. ICC runs once after authoritative WHO5 is frozen, using **Arber 2022 cards only**. WHO5 is supplied only so ICC can state whether the classifications are significantly different.
5. Other diagnostic considerations run separately from the case + authoritative WHO5 only; ICC is not supplied.
6. One proforma pass each for prognosis, treatment, biomarker/MRD and germline. Every variant must be covered. Each call injects shared PTBG interpretation discipline plus a domain-specific semantic boundary file before the small YAML proforma; the schema and interpretation policy are separate assets.
7. Build all evidence-bearing reasons, then perform **one batched evidence-match call** and **one batched evidence-audit call**. Obvious mismatches are reconsidered in bounded batches; advisory concerns are logged rather than allowed to veto the matcher.
8. Generate one reportable sentence per schema element.
9. In one planning call decide which reportable sentences to omit, split or merge. Python deterministically rearranges accepted parts into canonical domain blocks. A preservation audit can force a safe one-statement-per-block fallback.
10. Paraphrase all blocks in **one whole-report model call**. One batched preservation audit follows; unsafe blocks deterministically fall back to source-preserving text rather than launching per-sentence model loops.
11. Render citations deterministically from evidence ancestry through schema IDs → statement IDs → final blocks.

All model-produced structured artifacts pass through the shared v3 syntax-repair machinery before task validation. Deterministic validators accumulate all detectable issues in one pass. Only defects that can be repaired without changing informational content are classified as syntax/serialization problems. Clinical proformas allow at most **5 syntax-only repairs for one artifact**; if those fail, that artifact is abandoned and the original proforma task is regenerated from scratch. A clinical proforma may be fully rewritten at most **3 times** after its initial generation. Remaining content/coverage defects are returned together to the originating clinical task rather than being misrouted to syntax repair.

## CLI reference

```bash
python workflows/terraced_v4/step.py pipelines
python workflows/terraced_v4/step.py pipeline-check --pipeline self
python workflows/terraced_v4/step.py setup --mode ngs-report --case-file case.md --pipeline self
python workflows/terraced_v4/step.py run --work-dir <run-dir>
```

Use `--pipeline lmstudio` or `--pipeline openrouter` as configured in `pipelines/`.

## Run directory

- `model_steps/`: chronological model operations/prompts.
- `intermediates/`: machine-readable workflow state.
- `logs/workflow.log`: CLI/runtime log.
- `logs/model-usage.json`: provider-reported prompt/completion/total tokens for every direct-provider attempt, including syntax repair. `self` handoffs cannot report token usage and are not estimated.
- `logs/risk_log.yaml`: non-gating evidence/summarisation risks and graceful degradations.
- `logs/errors/`: invalid/retried clinical and syntax-repair artifacts.
- root: final deliverables (`report-final.md`, `report-final.json`, validation ZIP where applicable) plus common immutable workflow input/state.

## Prototype limitations

WHO5 stops after at most two passes. If WHO5 pass 2 changes CMC again, the workflow logs the unresolved routing risk and does not perform a third redraw. Citation audit detects obvious mismatch and fidelity risk but does not claim to prove entailment or overrule the matcher. Negative PTBG buckets are coverage/audit state and do not automatically become report sentences.
PTBG semantic guardrails reduce cross-domain over-inference but do not replace curated clinical evidence; in particular, a positive germline-suspect call must be supported by the supplied case/evidence rather than model memory alone.
