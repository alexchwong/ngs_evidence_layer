# Model provider compatibility

NEL's canonical provider-backed workflow supports LM Studio and OpenRouter through provider profiles under `config/pipelines/`.

## LM Studio

**Supported LM Studio version: 0.3.29 or newer.** LM Studio 0.3.29 introduced the OpenAI-compatible `POST /v1/responses` endpoint used by NEL. NEL uses `/v1/responses` for both synchronous and streamed LM Studio inference so provider-supplied reasoning and the final answer can be handled separately.

The default LM Studio base URL remains:

```text
http://localhost:1234/v1
```

For each model role, `reasoning` may be:

- `default` — omit `reasoning.effort` and use the model/server default;
- `low`;
- `medium`;
- `high`.

Reasoning support still depends on the loaded model. A model may expose no reasoning text even when a reasoning effort is requested.

NEL retains a compatibility fallback to `/v1/chat/completions` when `/v1/responses` is unavailable **only when the role uses `reasoning: default`**. This fallback is not the supported LM Studio transport and exists only to avoid an unnecessary hard failure on older/local OpenAI-compatible servers. If a non-default LM Studio reasoning level is requested, NEL will not silently drop it; an LM Studio server without `/v1/responses` fails with an upgrade message.

## OpenRouter

OpenRouter continues to use `/chat/completions`. Per-role reasoning accepts:

```text
default | none | minimal | low | medium | high | xhigh
```

`default` omits the reasoning parameter. Other levels are sent as `reasoning: {effort: <level>}`. Actual support remains model/provider dependent.

## Browser UI

The provider-profile editor adapts the reasoning dropdown to the selected provider class:

- LM Studio: `Default`, `Low`, `Medium`, `High`;
- OpenRouter: the full OpenRouter reasoning list;
- Other OpenAI-compatible providers: `Default` only.

The live **Model activity** panel shows provider-supplied reasoning separately from model output. This display is transient UI state and is not part of the clinical evidence/provenance artifacts.
