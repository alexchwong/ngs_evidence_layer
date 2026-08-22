# Terraced-v3 pipelines

A pipeline is the normal user-facing configuration unit. It selects one scheduler for each reasoning phase and binds every model role to a provider/model/token cap. Pipelines contain **composition and model configuration only**; information flow within a phase belongs in that phase's scheduler YAML.

## Shipped pipelines

- `self.yaml` — current session model; default diagnosis + domain PTBG + default summarization.
- `lmstudio.yaml` — LM Studio OpenAI-compatible endpoint.
- `openrouter.yaml` — OpenRouter OpenAI-compatible endpoint.

## Pipeline schema

```yaml
pipeline:
  id: self
  version: 1
  description: ...
provider:
  type: self                       # or openai-compatible
schedulers:
  diagnosis: default-diagnosis
  ptbg: domain
  summarization: default-summarization
models:
  structure: {model: self, temperature: 0.0, max_tokens: 16384}
  diagnosis: {model: self, temperature: 0.0, max_tokens: 32768}
  ptbg: {model: self, temperature: 0.0, max_tokens: 32768}
  evidence_alignment: {model: self, temperature: 0.0, max_tokens: 16384}
  summarization: {model: self, temperature: 0.0, max_tokens: 16384}
  summarization_review: {model: self, temperature: 0.0, max_tokens: 16384}
  syntax_repair: {model: self, temperature: 0.0, max_tokens: 8192}
```

OpenAI-compatible providers may additionally specify `base_url`, `base_url_env`, `api_key_env`, and `timeout_s`.

Every role is mandatory so a pipeline fully records the intended model environment. Multiple roles may point to the same model.

## Development commands

```bash
python workflows/terraced_v3/step.py pipelines
python workflows/terraced_v3/step.py pipeline-check --pipeline self
python workflows/terraced_v3/step.py pipeline-plan --pipeline self
```

`pipeline-check` validates provider/model settings and every scheduler selected by the pipeline. `pipeline-plan` also prints the three scheduler execution plans.

During `setup`, the resolved pipeline (including CLI scheduler overrides) is copied to `intermediates/*_setup/pipeline-resolved.yaml` so an existing run is insulated from later repository configuration edits.
