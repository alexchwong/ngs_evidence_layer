#!/usr/bin/env python3
"""Minimal OpenAI-compatible chat client for delegated categorical-v1 model steps.

Standard library only. Introducing an HTTP dependency for local inference would
be a poor trade against the existing thin requirements.txt.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from workflows.categorical_v1.model_registry import Binding

SYSTEM_PROMPT = (
    "You are executing one step of a clinical NGS reporting workflow.\n"
    "The user message contains every instruction and every file you are permitted to use "
    "for this step. No other source of information may be used: not your own knowledge of "
    "the literature, not files you have seen before, and not content you infer must exist.\n"
    "Reply with the complete content of the requested output file and nothing else. "
    "Do not add commentary, explanation, headings that were not requested, or a code fence."
)


class SelfExecution(RuntimeError):
    """Raised when complete() is called with a `self` binding."""


def _endpoint(binding: Binding) -> str:
    return f"{binding.base_url.rstrip('/')}/chat/completions"


class TruncatedCompletion(RuntimeError):
    """The provider stopped generating before finishing, most often max_tokens."""

    def __init__(self, content: str, max_tokens: int):
        self.content = content
        self.max_tokens = max_tokens
        super().__init__(
            f"provider stopped generating before the response was complete "
            f"(finish_reason=length, max_tokens={max_tokens}). The output is truncated, "
            "not wrong: raise max_tokens for this role rather than retrying as-is."
        )


def complete(binding: Binding, system: str, user: str) -> str:
    """Send one non-streaming completion request and return the message content."""
    if binding.is_self:
        raise SelfExecution(
            f"role {binding.role!r} is bound to the session model under profile "
            f"{binding.profile!r}; the driver must hand off instead of calling a provider"
        )

    payload = {
        "model": binding.model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": binding.temperature,
        "max_tokens": binding.max_tokens,
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    if binding.api_key:
        headers["Authorization"] = f"Bearer {binding.api_key}"

    request = urllib.request.Request(
        _endpoint(binding),
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=binding.timeout_s) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:800]
        raise RuntimeError(
            f"provider returned HTTP {exc.code} for model {binding.model!r} at "
            f"{_endpoint(binding)}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        override = binding.base_url_env or "the provider base URL"
        raise RuntimeError(
            f"provider endpoint is unreachable at {_endpoint(binding)}: {exc.reason}. "
            f"Confirm the inference server is running and serving an OpenAI-compatible API, "
            f"or override the endpoint by setting {override}."
        ) from exc
    except TimeoutError as exc:
        raise RuntimeError(
            f"provider request timed out after {binding.timeout_s}s at {_endpoint(binding)}"
        ) from exc

    try:
        document = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"provider returned a malformed JSON completion: {body[:400]}"
        ) from exc

    try:
        content = document["choices"][0]["message"]["content"]
        finish_reason = document["choices"][0].get("finish_reason")
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(
            f"provider completion has no message content: {body[:400]}"
        ) from exc

    if not isinstance(content, str) or not content.strip():
        raise RuntimeError(
            f"provider returned an empty completion for model {binding.model!r}"
        )

    if finish_reason == "length":
        raise TruncatedCompletion(content, binding.max_tokens)

    return content


def strip_code_fence(text: str) -> str:
    """Remove at most one wrapping code fence.

    Small models fence their output regardless of instruction; stripping is
    cheaper than a retry.
    """
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text
    lines = stripped.splitlines()
    if len(lines) < 2:
        return text
    closing = None
    for index in range(len(lines) - 1, 0, -1):
        if lines[index].strip().startswith("```"):
            closing = index
            break
    if closing is None or closing == 0:
        return text
    return "\n".join(lines[1:closing]).strip() + "\n"
