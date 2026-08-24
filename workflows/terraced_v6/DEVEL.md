# Terraced v6 developer notes

V6 is intentionally smaller than v5.

## Core assets

- `step.py` — orchestration, evidence flow, reportability, deterministic block assembly, dissent.
- `runtime.py` — case/setup validation and small deterministic helpers.
- `schema_validation.py` — lean owner/evidence/writer schemas.
- `settings.json.template` — retry, authority, retrieval, and reportability policy.
- `prompts/` — only active model tasks. There are no statement-generation, summary-plan, or paraphrase prompts.
- `pipelines/` — model bindings for self, LM Studio, and OpenRouter.

Clinical interpretation belongs to the owner call. Downstream code must not re-diagnose or repair owner clinical reasoning.
