# Terraced-v5

Use `workflows/terraced_v5/step.py` for the experimental v5 semantic-audit workflow. Set up a run, then repeatedly invoke `run`; the `self` pipeline returns HANDOFF/PROMPT/OUTPUT until the requested artifact is supplied, while LM Studio/OpenRouter call their configured OpenAI-compatible endpoints directly. Workflow policy and retry hyperparameters are in `settings.json`; shared prompt policy is injected at runtime through prompt includes.
