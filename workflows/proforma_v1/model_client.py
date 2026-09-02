#!/usr/bin/env python3
"""Provider client used by proforma-v1 pipeline model bindings.

LM Studio uses the OpenAI-compatible Responses API; OpenRouter and generic
OpenAI-compatible providers use Chat Completions.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import urlparse
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scripts import model_usage, run_layout

from workflows.proforma_v1.model_binding import Binding
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
    usage: dict[str, object] | None = None
    generation_id: str | None = None


class TruncatedCompletion(RuntimeError):
    def __init__(
        self,
        content: str,
        max_tokens: int,
        usage: dict[str, object] | None = None,
        generation_id: str | None = None,
    ):
        self.content = content
        self.max_tokens = max_tokens
        self.usage = usage
        self.generation_id = generation_id
        super().__init__(f"provider truncated output at max_tokens={max_tokens}")


class _StreamingUnsupported(RuntimeError):
    """The provider rejected or did not implement streaming on the selected endpoint."""


class _ResponsesUnsupported(RuntimeError):
    """LM Studio does not expose the OpenAI-compatible Responses endpoint."""


LMSTUDIO_MIN_VERSION = "0.3.29"
LMSTUDIO_REASONING_LEVELS = {"low", "medium", "high"}


def _is_lmstudio(binding: Binding) -> bool:
    try:
        host = (urlparse(binding.base_url).hostname or "").lower()
    except Exception:
        host = ""
    selector = str(binding.pipeline or "").strip().lower()
    return host in {"localhost", "127.0.0.1", "::1"} or selector.startswith("lmstudio")


def _endpoint(binding: Binding, *, transport: str | None = None) -> str:
    selected = transport or ("responses" if _is_lmstudio(binding) else "chat")
    suffix = "responses" if selected == "responses" else "chat/completions"
    return f"{binding.base_url.rstrip('/')}/{suffix}"


def _usage(document: dict) -> dict[str, object] | None:
    return model_usage.normalize_provider_usage(document)


def _argv_value(flag: str) -> str:
    try:
        index = sys.argv.index(flag)
    except ValueError:
        return ""
    return str(sys.argv[index + 1]).strip() if index + 1 < len(sys.argv) else ""


def _activity_path() -> Path | None:
    """Resolve the transient UI activity file outside the run artifact tree."""
    explicit = str(os.environ.get("NEL_MODEL_ACTIVITY_FILE") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()

    activity_dir = str(os.environ.get("NEL_MODEL_ACTIVITY_DIR") or "").strip()
    if not activity_dir:
        return None
    run_ref = _argv_value("--run-id")
    identity = run_ref
    if run_ref:
        try:
            run_layout.split_run_ref(run_ref)
        except run_layout.LayoutError:
            return None
    else:
        work_dir = _argv_value("--work-dir")
        if not work_dir:
            return None
        identity = str(Path(work_dir).expanduser().resolve())
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return Path(activity_dir).expanduser().resolve() / f"{digest}.jsonl"


class _ActivityWriter:
    """Best-effort transient JSONL feed for the UI; never gates a model call."""

    def __init__(self, binding: Binding):
        self.binding = binding
        self.path = _activity_path()
        self.handle = None
        self.reasoning_exposed = False

    def __enter__(self) -> "_ActivityWriter":
        if self.path is None:
            return self
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # The transient session feed is append-only so the UI can use the
            # same byte-offset polling semantics as the console. Rotate only at
            # a model-call boundary if an unusually long session exceeds 4 MiB.
            if self.path.is_file() and self.path.stat().st_size > 4 * 1024 * 1024:
                self.path.unlink()
            self.handle = self.path.open("a", encoding="utf-8", buffering=1)
            self.emit(
                "start",
                role=self.binding.role,
                model=self.binding.model,
                pipeline=self.binding.pipeline,
                reasoning=self.binding.reasoning,
                provider=model_usage.provider_name(
                    base_url=self.binding.base_url,
                    pipeline=self.binding.pipeline,
                ),
            )
        except OSError:
            self.handle = None
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.handle is not None:
            try:
                self.handle.close()
            except OSError:
                pass
            self.handle = None

    def emit(self, event: str, **fields: Any) -> None:
        if self.handle is None:
            return
        row = {"event": event, "time": time.time(), **fields}
        try:
            self.handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
            self.handle.flush()
        except OSError:
            try:
                self.handle.close()
            except OSError:
                pass
            self.handle = None

    def reasoning(self, text: str) -> None:
        if text:
            self.reasoning_exposed = True
            self.emit("reasoning", text=text)

    def output(self, text: str) -> None:
        if text:
            self.emit("output", text=text)


def _headers(binding: Binding) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if binding.api_key:
        headers["Authorization"] = f"Bearer {binding.api_key}"
    return headers


def _is_openrouter(binding: Binding) -> bool:
    try:
        host = (urlparse(binding.base_url).hostname or "").lower()
    except Exception:
        return False
    return host == "openrouter.ai" or host.endswith(".openrouter.ai")


def _reasoning_request(binding: Binding) -> dict[str, Any] | None:
    """Translate the provider-neutral role setting to the selected provider API."""
    effort = str(binding.reasoning or "default").strip().lower()
    if effort == "default":
        return None
    if _is_openrouter(binding):
        return {"effort": effort}
    if _is_lmstudio(binding):
        if effort not in LMSTUDIO_REASONING_LEVELS:
            allowed = ", ".join(sorted(LMSTUDIO_REASONING_LEVELS))
            raise RuntimeError(
                f"LM Studio reasoning effort {effort!r} is unsupported by NEL; "
                f"choose default, {allowed}"
            )
        return {"effort": effort}
    return None


def _payload(
    binding: Binding,
    messages: list[dict[str, str]],
    *,
    stream: bool,
    transport: str | None = None,
) -> dict[str, Any]:
    selected = transport or ("responses" if _is_lmstudio(binding) else "chat")
    if selected == "responses":
        payload: dict[str, Any] = {
            "model": binding.model,
            "input": messages,
            "temperature": binding.temperature,
            "max_output_tokens": binding.max_tokens,
            "stream": stream,
        }
    else:
        payload = {
            "model": binding.model,
            "messages": messages,
            "temperature": binding.temperature,
            "max_tokens": binding.max_tokens,
            "stream": stream,
        }
        if binding.provider_routing is not None:
            payload["provider"] = binding.provider_routing
    reasoning = _reasoning_request(binding)
    if reasoning is not None and (selected == "responses" or _is_openrouter(binding)):
        payload["reasoning"] = reasoning
    return payload


def _request(
    binding: Binding,
    payload: dict[str, Any],
    *,
    transport: str | None = None,
):
    return urllib.request.Request(
        _endpoint(binding, transport=transport),
        data=json.dumps(payload).encode("utf-8"),
        headers=_headers(binding),
        method="POST",
    )


def _http_error(
    binding: Binding,
    exc: urllib.error.HTTPError,
    *,
    transport: str | None = None,
) -> RuntimeError:
    detail = exc.read().decode("utf-8", errors="replace")[:1000]
    return RuntimeError(
        f"provider returned HTTP {exc.code} for {binding.model!r} "
        f"at {_endpoint(binding, transport=transport)}: {detail}"
    )


def _lmstudio_responses_required(binding: Binding, detail: str = "") -> RuntimeError:
    suffix = f" ({detail})" if detail else ""
    return RuntimeError(
        f"LM Studio {LMSTUDIO_MIN_VERSION}+ is required for NEL's /v1/responses transport"
        f"{suffix}. Upgrade LM Studio or use reasoning=default to allow the legacy "
        "chat-completions compatibility fallback."
    )


def _read_json_response(binding: Binding, request, *, transport: str) -> tuple[dict[str, Any], str]:
    try:
        with urllib.request.urlopen(request, timeout=binding.timeout_s) as response:
            body = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if transport == "responses" and exc.code in {404, 405}:
            try:
                exc.read()
            except OSError:
                pass
            raise _ResponsesUnsupported(f"HTTP {exc.code}") from exc
        raise _http_error(binding, exc, transport=transport) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"provider endpoint unreachable at {_endpoint(binding, transport=transport)}: {exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise RuntimeError(f"provider request timed out after {binding.timeout_s}s") from exc
    try:
        document = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"malformed provider completion: {body[:600]}") from exc
    if not isinstance(document, dict):
        raise RuntimeError(f"malformed provider completion: {body[:600]}")
    return document, body


def _complete_chat_nonstreaming(
    binding: Binding,
    messages: list[dict[str, str]],
    activity: _ActivityWriter | None = None,
) -> Completion:
    transport = "chat"
    request = _request(
        binding,
        _payload(binding, messages, stream=False, transport=transport),
        transport=transport,
    )
    document, body = _read_json_response(binding, request, transport=transport)
    try:
        choice = document["choices"][0]
        message = choice["message"]
        content = message["content"]
        reasoning = _reasoning_fragment(message) if isinstance(message, dict) else ""
        finish_reason = choice.get("finish_reason")
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"malformed provider completion: {body[:600]}") from exc
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("provider returned an empty completion")
    usage = _usage(document)
    generation_id = model_usage.generation_id(document)
    if activity is not None:
        if reasoning:
            activity.reasoning(reasoning)
        activity.output(content)
        activity.emit(
            "finish",
            finish_reason=finish_reason,
            reasoning_exposed=activity.reasoning_exposed,
            streamed=False,
            transport="chat/completions",
        )
    if finish_reason == "length":
        raise TruncatedCompletion(content, binding.max_tokens, usage, generation_id)
    return Completion(content, usage, generation_id)


def _responses_output(document: dict[str, Any]) -> str:
    parts: list[str] = []
    output = document.get("output")
    if not isinstance(output, list):
        return ""
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        content = item.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") in {"output_text", "text"}:
                text = part.get("text")
                if isinstance(text, str):
                    parts.append(text)
    return "".join(parts)


def _responses_reasoning(document: dict[str, Any]) -> str:
    parts: list[str] = []
    output = document.get("output")
    if not isinstance(output, list):
        return ""
    for item in output:
        if not isinstance(item, dict) or item.get("type") != "reasoning":
            continue
        for key in ("summary", "content", "text"):
            text = _text_fragment(item.get(key))
            if text:
                parts.append(text)
                break
    return "".join(parts)


def _responses_finish_reason(document: dict[str, Any]) -> str | None:
    status = str(document.get("status") or "").strip().lower()
    details = document.get("incomplete_details")
    reason = str(details.get("reason") or "").strip() if isinstance(details, dict) else ""
    if status == "incomplete":
        return reason or "incomplete"
    return "stop" if status == "completed" else (status or None)


def _responses_is_truncated(document: dict[str, Any]) -> bool:
    if str(document.get("status") or "").strip().lower() != "incomplete":
        return False
    details = document.get("incomplete_details")
    reason = str(details.get("reason") or "").strip().lower() if isinstance(details, dict) else ""
    return reason in {"max_output_tokens", "max_tokens", "length"}


def _complete_responses_nonstreaming(
    binding: Binding,
    messages: list[dict[str, str]],
    activity: _ActivityWriter | None = None,
) -> Completion:
    transport = "responses"
    request = _request(
        binding,
        _payload(binding, messages, stream=False, transport=transport),
        transport=transport,
    )
    document, body = _read_json_response(binding, request, transport=transport)
    content = _responses_output(document)
    reasoning = _responses_reasoning(document)
    if not content.strip():
        raise RuntimeError(f"provider returned an empty completion: {body[:600]}")
    usage = _usage(document)
    generation_id = model_usage.generation_id(document)
    finish_reason = _responses_finish_reason(document)
    if activity is not None:
        if reasoning:
            activity.reasoning(reasoning)
        activity.output(content)
        activity.emit(
            "finish",
            finish_reason=finish_reason,
            reasoning_exposed=activity.reasoning_exposed,
            streamed=False,
            transport="responses",
        )
    if _responses_is_truncated(document):
        raise TruncatedCompletion(content, binding.max_tokens, usage, generation_id)
    if str(document.get("status") or "").strip().lower() in {"failed", "cancelled"}:
        raise RuntimeError(f"LM Studio response ended with status {document.get('status')!r}")
    return Completion(content, usage, generation_id)


def _complete_nonstreaming(
    binding: Binding,
    messages: list[dict[str, str]],
    activity: _ActivityWriter | None = None,
) -> Completion:
    if not _is_lmstudio(binding):
        return _complete_chat_nonstreaming(binding, messages, activity)
    try:
        return _complete_responses_nonstreaming(binding, messages, activity)
    except _ResponsesUnsupported as exc:
        if str(binding.reasoning or "default").strip().lower() != "default":
            raise _lmstudio_responses_required(binding, str(exc)) from exc
        if activity is not None:
            activity.emit(
                "fallback",
                message=(
                    f"LM Studio /v1/responses is unavailable; using legacy chat completions. "
                    f"NEL supports LM Studio {LMSTUDIO_MIN_VERSION}+ for the canonical transport."
                ),
                detail=str(exc),
            )
        return _complete_chat_nonstreaming(binding, messages, activity)

def _text_fragment(value: Any) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, list):
        return ""
    parts: list[str] = []
    for item in value:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            text = item.get("text") or item.get("content")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def _reasoning_details_fragment(details: Any) -> str:
    """Return one canonical textual view of structured reasoning details.

    OpenRouter may expose the same reasoning through both the legacy/plaintext
    ``reasoning`` field and the structured ``reasoning_details`` array.  The
    structured representation therefore takes precedence; it must not be
    concatenated with the compatibility aliases or every streamed token can
    appear twice in the UI.

    Prefer raw ``reasoning.text`` chunks.  Only fall back to summaries when a
    chunk contains no textual reasoning.  Encrypted/opaque details are ignored.
    """
    if not isinstance(details, list):
        return ""

    text_parts: list[str] = []
    summary_parts: list[str] = []
    for item in details:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type") or "").strip().lower()
        text = item.get("text")
        summary = item.get("summary")

        if isinstance(text, str) and text and item_type != "reasoning.encrypted":
            text_parts.append(text)
        elif isinstance(summary, str) and summary:
            summary_parts.append(summary)

    if text_parts:
        return "".join(text_parts)
    return "".join(summary_parts)


def _reasoning_fragment(delta: dict[str, Any]) -> str:
    # OpenRouter documents reasoning_details as the standardized structured
    # representation.  Some providers also mirror the same delta in
    # ``reasoning`` / ``reasoning_content``.  Select exactly one representation
    # instead of concatenating aliases, otherwise live reasoning is duplicated.
    structured = _reasoning_details_fragment(delta.get("reasoning_details"))
    if structured:
        return structured

    for key in ("reasoning", "reasoning_content", "thinking"):
        text = _text_fragment(delta.get(key))
        if text:
            return text
    return ""


def _open_stream(binding: Binding, request, *, transport: str):
    try:
        return urllib.request.urlopen(request, timeout=binding.timeout_s)
    except urllib.error.HTTPError as exc:
        if transport == "responses" and exc.code in {404, 405}:
            try:
                exc.read()
            except OSError:
                pass
            raise _ResponsesUnsupported(f"HTTP {exc.code}") from exc
        # These statuses commonly indicate an endpoint that does not accept
        # streaming or a streaming-only request parameter.
        if exc.code in {400, 415, 422}:
            try:
                exc.read()
            except OSError:
                pass
            raise _StreamingUnsupported(f"HTTP {exc.code}") from exc
        raise _http_error(binding, exc, transport=transport) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"provider endpoint unreachable at {_endpoint(binding, transport=transport)}: {exc.reason}"
        ) from exc
    except TimeoutError as exc:
        raise RuntimeError(f"provider request timed out after {binding.timeout_s}s") from exc


def _complete_chat_streaming(
    binding: Binding,
    messages: list[dict[str, str]],
    activity: _ActivityWriter,
) -> Completion:
    transport = "chat"
    request = _request(
        binding,
        _payload(binding, messages, stream=True, transport=transport),
        transport=transport,
    )
    response = _open_stream(binding, request, transport=transport)
    saw_event = False
    saw_done = False
    content_parts: list[str] = []
    usage: dict[str, object] | None = None
    generation_id: str | None = None
    finish_reason: str | None = None

    try:
        with response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or line.startswith(":"):
                    continue
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data:
                    continue
                if data == "[DONE]":
                    saw_done = True
                    break
                try:
                    document = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if not isinstance(document, dict):
                    continue
                saw_event = True
                current_usage = _usage(document)
                if current_usage is not None:
                    usage = current_usage
                current_generation_id = model_usage.generation_id(document)
                if current_generation_id:
                    generation_id = current_generation_id
                choices = document.get("choices")
                if not isinstance(choices, list) or not choices:
                    continue
                choice = choices[0]
                if not isinstance(choice, dict):
                    continue
                delta = choice.get("delta")
                if not isinstance(delta, dict):
                    delta = {}
                reasoning = _reasoning_fragment(delta)
                if reasoning:
                    activity.reasoning(reasoning)
                output = _text_fragment(delta.get("content"))
                if output:
                    content_parts.append(output)
                    activity.output(output)
                if choice.get("finish_reason") is not None:
                    finish_reason = str(choice.get("finish_reason"))
    except TimeoutError as exc:
        raise RuntimeError(f"provider request timed out after {binding.timeout_s}s") from exc
    except OSError as exc:
        if not saw_event and not content_parts:
            raise _StreamingUnsupported(str(exc)) from exc
        raise RuntimeError(f"provider stream failed for {binding.model!r}: {exc}") from exc

    if not saw_event:
        raise _StreamingUnsupported("provider returned no SSE completion events")
    content = "".join(content_parts)
    if not content.strip():
        raise RuntimeError("provider returned an empty completion")
    activity.emit(
        "finish",
        finish_reason=finish_reason,
        reasoning_exposed=activity.reasoning_exposed,
        streamed=True,
        done_marker=saw_done,
        transport="chat/completions",
    )
    if finish_reason == "length":
        raise TruncatedCompletion(content, binding.max_tokens, usage, generation_id)
    return Completion(content, usage, generation_id)


def _responses_event_reasoning(document: dict[str, Any]) -> str:
    event_type = str(document.get("type") or "").lower()
    if "reasoning" not in event_type or not event_type.endswith(".delta"):
        return ""
    return _text_fragment(document.get("delta"))


def _complete_responses_streaming(
    binding: Binding,
    messages: list[dict[str, str]],
    activity: _ActivityWriter,
) -> Completion:
    transport = "responses"
    request = _request(
        binding,
        _payload(binding, messages, stream=True, transport=transport),
        transport=transport,
    )
    response = _open_stream(binding, request, transport=transport)
    saw_event = False
    content_parts: list[str] = []
    usage: dict[str, object] | None = None
    generation_id: str | None = None
    final_response: dict[str, Any] | None = None

    try:
        with response:
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line or line.startswith(":") or not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if not data or data == "[DONE]":
                    continue
                try:
                    document = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if not isinstance(document, dict):
                    continue
                saw_event = True
                event_type = str(document.get("type") or "")
                if event_type == "response.output_text.delta":
                    output = _text_fragment(document.get("delta"))
                    if output:
                        content_parts.append(output)
                        activity.output(output)
                else:
                    reasoning = _responses_event_reasoning(document)
                    if reasoning:
                        activity.reasoning(reasoning)
                nested = document.get("response")
                if isinstance(nested, dict):
                    current_generation_id = model_usage.generation_id(nested)
                    if current_generation_id:
                        generation_id = current_generation_id
                    current_usage = _usage(nested)
                    if current_usage is not None:
                        usage = current_usage
                    if event_type in {"response.completed", "response.incomplete", "response.failed"}:
                        final_response = nested
                current_generation_id = model_usage.generation_id(document)
                if current_generation_id and not generation_id:
                    generation_id = current_generation_id
    except TimeoutError as exc:
        raise RuntimeError(f"provider request timed out after {binding.timeout_s}s") from exc
    except OSError as exc:
        if not saw_event and not content_parts:
            raise _StreamingUnsupported(str(exc)) from exc
        raise RuntimeError(f"provider stream failed for {binding.model!r}: {exc}") from exc

    if not saw_event:
        raise _StreamingUnsupported("provider returned no SSE response events")
    content = "".join(content_parts)
    if not content.strip() and final_response is not None:
        content = _responses_output(final_response)
        if content:
            activity.output(content)
        reasoning = _responses_reasoning(final_response)
        if reasoning and not activity.reasoning_exposed:
            activity.reasoning(reasoning)
    if not content.strip():
        raise RuntimeError("provider returned an empty completion")
    finish_reason = _responses_finish_reason(final_response or {})
    activity.emit(
        "finish",
        finish_reason=finish_reason,
        reasoning_exposed=activity.reasoning_exposed,
        streamed=True,
        transport="responses",
    )
    if final_response is not None and _responses_is_truncated(final_response):
        raise TruncatedCompletion(content, binding.max_tokens, usage, generation_id)
    if final_response is not None and str(final_response.get("status") or "").lower() == "failed":
        raise RuntimeError("LM Studio response failed")
    return Completion(content, usage, generation_id)


def _complete_streaming(
    binding: Binding,
    messages: list[dict[str, str]],
    activity: _ActivityWriter,
) -> Completion:
    if not _is_lmstudio(binding):
        return _complete_chat_streaming(binding, messages, activity)
    try:
        return _complete_responses_streaming(binding, messages, activity)
    except _ResponsesUnsupported as exc:
        if str(binding.reasoning or "default").strip().lower() != "default":
            raise _lmstudio_responses_required(binding, str(exc)) from exc
        activity.emit(
            "fallback",
            message=(
                f"LM Studio /v1/responses is unavailable; using legacy chat completions. "
                f"NEL supports LM Studio {LMSTUDIO_MIN_VERSION}+ for the canonical transport."
            ),
            detail=str(exc),
        )
        return _complete_chat_streaming(binding, messages, activity)

def complete_messages(binding: Binding, messages: list[dict[str, str]]) -> Completion:
    if binding.is_self:
        raise SelfExecution(
            f"role {binding.role!r} is bound to the session model under profile {binding.profile!r}"
        )

    # The browser server opts provider calls into streaming. Direct CLI runs
    # remain non-streaming unless NEL_MODEL_STREAM is explicitly set.
    streaming = str(os.environ.get("NEL_MODEL_STREAM", "0")).strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }
    if not streaming:
        return _complete_nonstreaming(binding, messages)

    with _ActivityWriter(binding) as activity:
        try:
            return _complete_streaming(binding, messages, activity)
        except _StreamingUnsupported as exc:
            activity.emit(
                "fallback",
                message="Live streaming is unavailable from this model/provider; using completed response mode.",
                detail=str(exc),
            )
            try:
                return _complete_nonstreaming(binding, messages, activity)
            except Exception as fallback_exc:
                activity.emit("error", message=str(fallback_exc))
                raise
        except Exception as exc:
            activity.emit("error", message=str(exc))
            raise


def strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return text.rstrip() + "\n"
    lines = stripped.splitlines()
    if len(lines) >= 2 and lines[-1].strip().startswith("```"):
        return "\n".join(lines[1:-1]).strip() + "\n"
    return text.rstrip() + "\n"
