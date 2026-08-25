# Terraced v5 developer notes

Terraced-v5 is cloned from v4 but deliberately changes the semantic pipeline. V4 must remain untouched.

## Asset ownership

- `step.py`: orchestration, retry routing, model call boundaries, evidence/reportability flow.
- `schema_validation.py`: deterministic shape/ID/coverage validation only.
- `runtime.py`: deterministic CMC derivation, summary-plan validation/block construction, citation ancestry.
- `settings.json`: workflow decisions and hyperparameters. Do not add new retry counts, authority publication keys, CMC-pass limits, PTBG category policy or summary policy as Python literals.
- `pipelines/*.yaml`: provider/model bindings and model token limits.
- `prompts/*.md`: task-specific prompt entry points.
- `prompts/includes/*.md`: reusable semantic policy fragments.
- `prompt_loader.py`: recursive runtime `{{ include "..." }}` expansion with cycle/path protection.

## Authority configuration

WHO5/ICC authority publication keys are read only from `settings.json`. The code filters the current diagnosis card draw by those keys but does not know which paper/authors the keys represent. Adding another WHO5 authority is a settings/corpus change, not a Python change.

## Semantic boundaries

Each proforma is followed by:

1. atomic statement generation;
2. statement audit: `statement_represents_proforma` + `reasoning_status` (`supported`, `supported_if`, `unsupported`);
3. evidence match using `statement` as the primary target;
4. evidence audit: `quote_supports_statement` + `quote_supports_reason`.

A statement-level representation failure regenerates statements de novo. `reasoning_status: unsupported` returns negative guidance to the preceding proforma generation and regenerates that proforma de novo within settings-defined caps. Evidence mismatch rematches evidence. These failure owners must not be conflated.

## Shared audit policy

`prompts/includes/audit_general.md` is injected into every semantic audit. Auditors inspect only their adjacent boundary, distinguish pending discriminators from missing positive defining evidence, and provide negative guidance rather than replacement answers.

## Reportability and summary

Positive PTBG bucket definitions live in settings. If a positive PTBG statement is not evidence-resolved, it is suppressed from automatic publication but remains in intermediates and the risk log. Summary planning is model-driven omit/split/merge; final block ordering is deterministic and settings-driven. Final paraphrasing is one whole-report call with `case.md` supplied as context only.

## Retry/settings rule

All workflow retry and semantic-regeneration caps belong in `settings.json`. Syntax repair uses the shared core syntax machinery and has its own budget. Semantic retries regenerate from original inputs; they do not edit rejected semantic output.
