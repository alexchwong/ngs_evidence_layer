#!/usr/bin/env python3
"""OpenAI-compatible chat client used by terraced-v3 pipeline model bindings."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from workflows.terraced_v3.model_binding import Binding

SYSTEM_PROMPT = (
    "You are executing a bounded step of a clinical NGS reporting workflow. "
    "Use only the supplied case, evidence, prior accepted state, questions and instructions. "
    "Do not search the web or use outside literature. Return exactly the requested artifact."
)


class SelfExecution(RuntimeError):
    pass


@dataclass(frozen=True)
class Completion:
    """Provider completion plus exact usage metadata, when the provider supplies it."""

    content: str
    usage: dict[str, int] | None = None


class TruncatedCompletion(RuntimeError):
    def __init__(
        self,
        content: str,
        max_tokens: int,
        usage: dict[str, int] | None = None,
    ):
        self.content = content
        self.max_tokens = max_tokens
        self.usage = usage
        super().__init__(f"provider truncated output at max_tokens={max_tokens}")


def _endpoint(binding: Binding) -> str:
    return f"{binding.base_url.rstrip('/')}/chat/completions"


def _usage(document: dict) -> dict[str, int] | None:
    raw = document.get("usage")
    if not isinstance(raw, dict):
        return None
    aliases = {
        "prompt_tokens": ("prompt_tokens", "input_tokens"),
        "completion_tokens": ("completion_tokens", "output_tokens"),
        "total_tokens": ("total_tokens",),
    }
    usage = {}
    for canonical, names in aliases.items():
        value = next((raw.get(name) for name in names if raw.get(name) is not None), None)
        if isinstance(value, int) and value >= 0:
            usage[canonical] = value
    if "total_tokens" not in usage and {
        "prompt_tokens",
        "completion_tokens",
    } <= usage.keys():
        usage["total_tokens"] = usage["prompt_tokens"] + usage["completion_tokens"]
    return usage or None


def complete_messages(binding: Binding, messages: list[dict[str, str]]) -> Completion:
    if binding.is_self:
        raise SelfExecution(
            f"role {binding.role!r} is bound to the session model under profile {binding.profile!r}"
        )
    payload = {
        "model": binding.model,
        "messages": messages,
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
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise RuntimeError(
            f"provider returned HTTP {exc.code} for {binding.model!r} at {_endpoint(binding)}: {detail}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"provider endpoint unreachable at {_endpoint(binding)}: {exc.reason}") from exc
    except TimeoutError as exc:
        raise RuntimeError(f"provider request timed out after {binding.timeout_s}s") from exc
    try:
        document = json.loads(body)
        choice = document["choices"][0]
        content = choice["message"]["content"]
        finish_reason = choice.get("finish_reason")
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"malformed provider completion: {body[:600]}") from exc
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("provider returned an empty completion")
    usage = _usage(document)
    if finish_reason == "length":
        raise TruncatedCompletion(content, binding.max_tokens, usage)
    return Completion(content, usage)


def strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text.rstrip() + "\n"
    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[-1].strip().startswith("```"):
        return "\n".join(lines[1:-1]).strip() + "\n"
    return text.rstrip() + "\n"
