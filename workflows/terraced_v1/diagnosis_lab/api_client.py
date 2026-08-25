#!/usr/bin/env python3
"""Tiny OpenAI-compatible chat client for diagnosis_lab."""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderConfig:
    provider: str
    base_url: str
    model: str
    api_key: str = ""
    temperature: float = 0.0
    max_tokens: int = 16384
    timeout_s: float = 900.0

    @property
    def endpoint(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"


def config_for(
    provider: str,
    model: str,
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 16384,
    timeout_s: float = 900.0,
) -> ProviderConfig:
    provider = provider.lower().strip()
    if provider == "lmstudio":
        resolved_url = base_url or os.environ.get("NEL_LMSTUDIO_BASE_URL") or "http://localhost:1234/v1"
        resolved_key = api_key if api_key is not None else os.environ.get("NEL_LMSTUDIO_API_KEY", "")
    elif provider == "openrouter":
        resolved_url = base_url or os.environ.get("NEL_OPENROUTER_BASE_URL") or "https://openrouter.ai/api/v1"
        resolved_key = api_key if api_key is not None else os.environ.get("OPENROUTER_API_KEY", "")
        if not resolved_key:
            raise ValueError("OpenRouter requires --api-key or OPENROUTER_API_KEY")
    elif provider == "openai-compatible":
        if not base_url:
            raise ValueError("openai-compatible requires --base-url")
        resolved_url = base_url
        resolved_key = api_key or ""
    else:
        raise ValueError("provider must be lmstudio, openrouter, or openai-compatible")
    if not model.strip():
        raise ValueError("--model must be non-empty")
    return ProviderConfig(
        provider=provider,
        base_url=resolved_url,
        model=model,
        api_key=resolved_key,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout_s=timeout_s,
    )


def complete(config: ProviderConfig, messages: list[dict[str, str]]) -> str:
    payload = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
        "max_tokens": config.max_tokens,
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"
    if config.provider == "openrouter":
        headers.setdefault("HTTP-Referer", "https://github.com/alexchwong/ngs_evidence_layer")
        headers.setdefault("X-Title", "NGS Evidence Layer diagnosis lab")
    request = urllib.request.Request(
        config.endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=config.timeout_s) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1200]
        raise RuntimeError(f"provider HTTP {exc.code} at {config.endpoint}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"provider endpoint unreachable at {config.endpoint}: {exc.reason}") from exc
    try:
        document = json.loads(body)
        content = document["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"malformed provider completion: {body[:800]}") from exc
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("provider returned empty completion")
    return _strip_fence(content)


def _strip_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped + "\n"
    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[-1].strip().startswith("```"):
        return "\n".join(lines[1:-1]).strip() + "\n"
    return stripped + "\n"
