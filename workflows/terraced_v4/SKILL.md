# Terraced-v4

Use `workflows/terraced_v4/step.py` for the experimental v4 proforma workflow. Set up a run, then repeatedly invoke `run`; `self` pipeline invocations return HANDOFF/PROMPT/OUTPUT until the requested artifact is supplied, while LM Studio/OpenRouter pipelines call their configured OpenAI-compatible endpoints directly.
