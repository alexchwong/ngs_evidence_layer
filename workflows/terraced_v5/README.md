# Terraced v5

Terraced-v5 is a major refactor cloned from terraced-v4. It keeps v4 provider plumbing, case initialization, CMC routing, run layout, syntax repair, risk logging, token accounting and category-specific PTBG card retrieval, but makes the semantic provenance chain explicit:

`proforma → atomic statement → statement/reason audit → evidence match → statement/reason-vs-quote audit → reportability → omit/split/merge → deterministic blocks → one final paraphrase`.

## Quick start

List shipped pipelines:

```bash
python workflows/terraced_v5/step.py pipelines
```

Validate a pipeline before running it:

```bash
python workflows/terraced_v5/step.py pipeline-check --pipeline self
```

Run validation brief case 1 with the self pipeline:

```bash
python workflows/terraced_v5/step.py setup \
  --mode nel-validate-brief \
  --case-id 1 \
  --pipeline self
```

Then continue the scripted run:

```bash
python workflows/terraced_v5/step.py run --work-dir <run-directory>
```

For `self`, the CLI emits model handoffs to be completed by the session model. LM Studio and OpenRouter pipelines call their configured OpenAI-compatible endpoints directly.

## Workflow

1. Structure `case.md` and create stable variant IDs (`v01`, `v02`, ...).
2. WHO5 runs first. WHO5 alone drives CMC routing. If CMC changes, a fresh WHO5 pass is performed up to the configured pass limit.
3. ICC runs after authoritative WHO5 and receives WHO5 for comparison only.
4. Other diagnostic considerations receive authoritative WHO5 only.
5. Prognosis, treatment, biomarker/MRD and germline each receive only their own card category.
6. Every authoritative proforma is converted into atomic reportable statements.
7. A statement audit checks both faithful representation of the proforma and whether the supplied reason actually justifies the statement. Missing discriminator information may support a qualified `supported_if`; missing positive defining evidence cannot be invented conditionally.
8. Evidence is matched to the **statement**, with the reason supplied as context.
9. Evidence audit separately tests whether the quote supports the statement and whether it supports the reason.
10. Positive PTBG statements that remain semantically or evidentially unresolved are retained in intermediates/risk logs but are not automatically published.
11. One model pass decides omit/split/merge. Python deterministically constructs ordered same-category report blocks.
12. One final whole-report paraphrase pass receives all blocks plus `case.md` as context only, followed by one preservation audit.

## Settings-driven workflow policy

`settings.json` is the workflow policy/hyperparameter file. It contains:

- provider pipeline selection;
- every retry/regeneration budget;
- WHO5 and ICC authority `publication_keys`;
- maximum WHO5 CMC passes;
- PTBG card category and positive-bucket definitions;
- unresolved-reportability policy;
- summary domain order and cross-domain merge policy;
- prompt entry-point assets.

For example, WHO5 currently uses the configured myeloid authority publication key. A future WHO5 lymphoid authority can be added by appending its `publication_key` under `diagnosis.who5.publication_keys`; Python does not name Khoury/Alaggio or otherwise hardcode that authority choice.

## Modular prompts and runtime includes

Prompt assets can inject shared prompt assets at runtime:

```text
{{ include "includes/audit_general.md" }}
```

Includes are recursive, resolved inside `prompts/`, and protected against cycles/path escape. PTBG prompts inject shared PTBG discipline plus their domain-specific semantic boundaries. Semantic audit prompts inject the common audit principles.

## Retry philosophy

- Syntax/serialization defects use shared generic syntax repair and do not consume semantic regeneration attempts.
- Clinical proformas use the configured syntax cap and full-proforma rewrite cap.
- Semantic audit failures regenerate de novo from original inputs with auditor feedback only as negative guidance; rejected semantic output is not used as the starting draft.
- Evidence failures rematch evidence rather than silently rewriting the clinical statement.
- Safely degradable failures are logged and preserve source content.

## Run directory

- `model_steps/`: chronological model prompts/outputs.
- `intermediates/`: accepted structured state and audit artifacts.
- `logs/workflow.log`: CLI/runtime progression.
- `logs/model-usage.json`: provider-reported token usage.
- `logs/risk_log.yaml`: semantic/evidence/degradation risks.
- `logs/errors/`: rejected model and syntax-repair artifacts.
- run root: final report artifacts and common immutable run inputs/state.

## Prototype limitations

The semantic auditors are model-based critics, not deterministic clinical truth engines. The shared audit principles deliberately prefer a qualified `supported_if` over adversarial rejection when an already-supported conclusion depends on pending discriminator information. Positive PTBG claims may be withheld when the corpus lacks affirmatively supporting evidence; the underlying proforma remains auditable rather than being silently deleted.
