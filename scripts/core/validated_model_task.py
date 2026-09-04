"""Workflow-neutral structural validation and repair support for model tasks.

YAML/JSON syntax repair lives in `scripts.core.syntax_repair`. This module retains
lightweight cleanup for non-structured text plus workflow-neutral structured
validation issues and ordinary task-retry instructions. It never changes informational
content. Workflow/task validators remain responsible for domain invariants.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    problem: str
    required_fix: str
    repair_class: str = "shape"
    received: str | None = None
    expected: str | None = None

    def render(self, index: int) -> str:
        """Render one issue over several short lines.

        A single run-on line is harder for a small model to parse than a labelled
        block, and the field path is the part that most needs to survive: it is
        the only element that tells the model *where* to edit.
        """
        lines = [f"{index}. {self.path}"]
        lines.append(f"   Problem: {self.problem}.")
        lines.append(f"   Required fix: {self.required_fix}.")
        if self.received is not None:
            lines.append(f"   Received: {self.received}")
        if self.expected is not None:
            lines.append(f"   Expected: {self.expected}")
        return "\n".join(lines)


# A model asked to repair forty simultaneous defects repairs a prefix and stops.
# Report a bounded, representative set and say how many were withheld.
MAX_RENDERED_ISSUES = 8


def render_issues(issues: list[ValidationIssue], *, limit: int = MAX_RENDERED_ISSUES) -> str:
    shown = issues[:limit]
    body = "\n".join(issue.render(i) for i, issue in enumerate(shown, 1))
    hidden = len(issues) - len(shown)
    if hidden > 0:
        body += (
            f"\n\n{hidden} further issue(s) of the same kinds were not listed. "
            "Fix the listed issues and apply the same corrections throughout the artifact."
        )
    return body


class ValidationFailure(ValueError):
    """A model-fixable validation failure with structured actionable issues."""

    def __init__(self, context: str, issues: list[ValidationIssue]):
        self.context = context
        self.issues = list(issues)
        super().__init__(
            f"{context} failed validation with {len(self.issues)} issue(s):\n"
            + render_issues(self.issues)
        )


def fail(context: str, issues: list[ValidationIssue]) -> None:
    if issues:
        raise ValidationFailure(context, issues)


def safe_representation_repair(text: str) -> tuple[str, list[str]]:
    """Apply only serialization-preserving cleanup with no interpretive judgement."""
    original = text
    stripped = text.strip()
    repairs: list[str] = []
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            stripped = "\n".join(lines[1:-1])
            repairs.append("removed surrounding Markdown code fence")
    # Trailing whitespace is never meaningful to YAML/JSON structure and is a
    # recurrent source of exact-format failures in report lines.
    cleaned = "\n".join(line.rstrip() for line in stripped.splitlines()).strip()
    cleaned = cleaned + "\n" if cleaned else ""
    if cleaned != original and not repairs:
        repairs.append("normalised surrounding/trailing whitespace")
    return cleaned, repairs


def validate_with_safe_repair(
    raw_text: str,
    validator: Callable[[str], str],
) -> tuple[str, str, list[str]]:
    """Repair representation, then run the caller's task-specific validator."""
    candidate, repairs = safe_representation_repair(raw_text)
    message = validator(candidate)
    return candidate, message, repairs


class RetryStagnationGuard:
    """Track repeated identical invalid artifacts without altering retry policy.

    ``observe`` returns the number of consecutive repeats *after* the first
    occurrence of the same candidate/error pair.  A changed candidate or error
    resets the count.  Callers can use this to stop wasting task retries on
    a model that is returning the exact same invalid serialization.
    """

    def __init__(self) -> None:
        self._last: tuple[str, str] | None = None
        self._repeats = 0

    def observe(self, candidate: str, error: str) -> int:
        current = (candidate, error)
        if current == self._last:
            self._repeats += 1
        else:
            self._last = current
            self._repeats = 0
        return self._repeats


def stagnation_instruction(repeat_count: int) -> str:
    """Add concise repair feedback when the same invalid artifact is repeated.

    The caller owns the stopping policy.  This helper only tells the model that
    its previous repair did not materially change the rejected artifact.
    """
    if repeat_count <= 0:
        return ""
    return (
        "\n\nThe last repair repeated the same invalid artifact and validation error. "
        "Make a material correction to the stated validation issue; do not return the same artifact again."
    )


def retry_instruction(error: Exception) -> str:
    """Render one complete, self-contained repair request for the next model attempt."""
    if isinstance(error, ValidationFailure):
        detail = str(error)
    else:
        detail = str(error).strip() or type(error).__name__
    return (
        "The previous complete artifact failed deterministic validation. "
        "Return the complete artifact again, not a patch. Fix every issue below and preserve unrelated "
        "decisions and supplied IDs exactly. Do not troubleshoot the validator or add commentary.\n\n"
        + detail
    )


# ---------------------------------------------------------------------------
# Reusable validated-model-task runner
# ---------------------------------------------------------------------------
"""A workflow-neutral runner for "call a model, validate, repair, retry".

Three behaviours make this worth extracting rather than re-deriving, and all
three are preserved exactly:

1. **Suspension.** With an interactive pipeline a model call does not return a
   value: the process exits and a later invocation resumes. The runner therefore
   keeps all loop state in `io.load_state`/`io.save_state` and raises `Suspend`
   instead of owning an uninterruptible loop.
2. **Nested budgets.** A serialization budget sits inside a rewrite budget, with
   two distinct restart modes: `fresh` (discard the artifact, regenerate from the
   original task) and `repair` (replay the artifact with feedback).
3. **Serialization/content routing.** Issues classed `serialization` go to a
   syntax-repair model; only content issues return to the originating task, so
   the task is never asked to fix a quoted boolean.

The runner performs no filesystem access and holds no domain vocabulary: every
environment-specific action goes through `TaskIO`.
"""

import hashlib
from dataclasses import dataclass, field
from typing import Any, Callable


class Truncated:
    """A completion cut short by a provider token limit."""

    def __init__(self, content: str, *, max_tokens: int):
        self.content = content
        self.max_tokens = max_tokens


class TaskFailed(RuntimeError):
    """A task exhausted its budget, or stopped early because it was stagnating."""


class Suspend(Exception):
    """The runner needs a response it cannot obtain itself."""

    def __init__(self, task_id: str, messages: list[dict], feedback: str = ""):
        self.task_id = task_id
        self.messages = messages
        self.feedback = feedback
        super().__init__(task_id)


@dataclass(frozen=True)
class Budgets:
    content: int = 3
    serialization: int = 2
    rewrite: int = 1


@dataclass(frozen=True)
class TaskRequest:
    task_id: str
    messages: list[dict]
    validate: Callable[[str], str]
    budgets: Budgets
    fmt: str | None = None
    mode: str = "standard"          # 'standard' | 'proforma'
    prepare: Callable[[str], str] | None = None


@dataclass(frozen=True)
class TaskIO:
    call_model: Callable[[list[dict]], Any]
    load_state: Callable[[str], dict]
    save_state: Callable[[str, dict], None]
    read_output: Callable[[], str | None]
    write_output: Callable[[str], None]
    call_syntax_model: Callable[[str, int], str] | None = None
    record_attempt: Callable[[Any], None] = lambda attempt: None
    record_syntax_attempt: Callable[[Any], None] = lambda attempt: None
    status: Callable[[str], None] = lambda message: None
    is_self: bool = False


@dataclass
class Attempt:
    task_id: str
    index: int
    response: str
    error: str | None = None


@dataclass
class SyntaxAttempt:
    task_id: str
    index: int
    response: str
    error: str | None = None


# After this many consecutive identical (artifact, error) pairs another unchanged
# retry has no expected value; surface the deterministic failure instead.
STAGNATION_ABORT_AFTER = 2


def _fingerprint(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:16]


def _serialization_issues(error: Exception) -> list[ValidationIssue]:
    if not isinstance(error, ValidationFailure):
        return []
    return [issue for issue in error.issues if issue.repair_class == "serialization"]


def _content_error(error: Exception) -> str:
    """Render feedback for the originating task, excluding serialization defects."""
    if isinstance(error, ValidationFailure):
        content = [i for i in error.issues if i.repair_class != "serialization"]
        if content:
            return retry_instruction(ValidationFailure(error.context, content))
    return retry_instruction(error)


def _fresh_instruction(task_id: str, detail: str) -> str:
    return (
        "The previous complete artifact could not be made structurally valid. Regenerate the "
        "complete artifact from scratch from the original task and supplied context. Do not copy, "
        "patch, or troubleshoot the previous artifact. The structural problem was:\n\n" + str(detail).strip()
    )


def _truncation_instruction(max_tokens: int) -> str:
    return (
        f"The previous answer was truncated at max_tokens={max_tokens}. Return the complete "
        "artifact again from scratch, not a patch or a continuation."
    )


def _prepare(request: TaskRequest, raw: str) -> str:
    return request.prepare(raw) if request.prepare else raw


def _validate(request: TaskRequest, io: TaskIO, candidate: str) -> tuple[str, str]:
    """Validate, routing representation-only defects to the syntax model first."""
    try:
        return candidate, request.validate(candidate)
    except ValidationFailure as exc:
        serial = _serialization_issues(exc)
        if not serial or io.call_syntax_model is None or request.budgets.serialization <= 0:
            raise
    repaired = candidate
    for attempt in range(1, request.budgets.serialization + 1):
        feedback = render_issues(serial)
        prompt = (
            "Repair serialization only. Do not add, remove, or change informational content.\n\n"
            "Representation-only defects to fix:\n" + feedback + "\n\nCurrent artifact:\n" + repaired
        )
        io.status(f"  {request.task_id}: serialization repair {attempt}/{request.budgets.serialization}")
        repaired = _prepare(request, io.call_syntax_model(prompt, attempt))
        try:
            message = request.validate(repaired)
        except ValidationFailure as exc:
            serial = _serialization_issues(exc)
            io.record_syntax_attempt(SyntaxAttempt(request.task_id, attempt, repaired, str(exc)))
            if not serial:
                raise
        except Exception as exc:
            io.record_syntax_attempt(SyntaxAttempt(request.task_id, attempt, repaired, str(exc)))
            raise
        else:
            io.record_syntax_attempt(SyntaxAttempt(request.task_id, attempt, repaired))
            return repaired, message
    raise ValidationFailure(request.task_id, serial)


def _observe(state: dict, candidate: str, error: str) -> int:
    current = [_fingerprint(candidate), _fingerprint(error)]
    repeats = int(state.get("stagnation_repeats", 0)) + 1 if state.get("stagnation") == current else 0
    state["stagnation"] = current
    state["stagnation_repeats"] = repeats
    return repeats


def _guard(request: TaskRequest, io: TaskIO, state: dict, candidate: str, feedback: str) -> str:
    repeats = _observe(state, candidate, feedback)
    io.save_state(request.task_id, state)
    if repeats >= STAGNATION_ABORT_AFTER:
        raise TaskFailed(
            f"{request.task_id} returned the same rejected artifact and the same error "
            f"{repeats + 1} times; stopping early rather than retrying unchanged. "
            f"Last feedback:\n{feedback}"
        )
    if repeats > 0:
        io.status(f"  {request.task_id}: unchanged rejected artifact ({repeats + 1} identical attempts)")
        return feedback + stagnation_instruction(repeats)
    return feedback


def _messages(request: TaskRequest, previous: str | None, feedback: str, mode: str) -> list[dict]:
    out = list(request.messages)
    if mode == "fresh" and feedback:
        out.append({"role": "user", "content": feedback})
    elif previous is not None:
        out.append({"role": "assistant", "content": previous})
        out.append({"role": "user", "content": feedback})
    elif feedback:
        out.append({"role": "user", "content": feedback})
    return out


def _consume(request: TaskRequest, io: TaskIO, completion) -> tuple[str, str | None]:
    """Return (raw text, truncation feedback or None)."""
    if isinstance(completion, Truncated):
        return completion.content, _truncation_instruction(completion.max_tokens)
    content = getattr(completion, "content", completion)
    return content, None


def run(request: TaskRequest, io: TaskIO) -> str:
    """Execute one validated model task. Returns the accepted artifact.

    Raises `Suspend` when a response must come from outside the process, and
    `TaskFailed` when a budget is exhausted or the model is stagnating.
    """
    state = io.load_state(request.task_id)
    attempts = request.budgets.rewrite + 1 if request.mode == "proforma" else request.budgets.content
    index = int(state.get("rewrites", 0))
    mode = state.get("mode") or "initial"
    feedback = state.get("feedback") or ""
    previous = state.get("previous")

    existing = io.read_output()
    if existing is not None:
        existing_fp = _fingerprint(existing)
        # A native-self suspension is not a model attempt.  After an invalid
        # artifact has been consumed we persist its fingerprint; if the next
        # process invocation sees the same file, it must re-issue the same
        # repair handoff without incrementing the attempt counter again.
        already_consumed = state.get("consumed_output_fingerprint") == existing_fp
        if not already_consumed:
            try:
                candidate, message = _validate(request, io, _prepare(request, existing))
            except Exception as exc:
                feedback = _guard(request, io, state, existing, _content_error(exc))
                previous = existing
                mode = "repair"
                index += 1
                state.update({
                    "rewrites": index, "mode": mode, "feedback": feedback, "previous": previous,
                    "consumed_output_fingerprint": existing_fp,
                })
                io.save_state(request.task_id, state)
                io.record_attempt(Attempt(request.task_id, index, existing, feedback))
                if index >= attempts:
                    raise TaskFailed(f"{request.task_id} failed validation after {attempts} attempt(s): {feedback}")
            else:
                io.write_output(candidate)
                io.save_state(request.task_id, {})
                return candidate
        else:
            # Restore the persisted repair state verbatim.  This is the common
            # path when a host model has not yet replaced the rejected output.
            previous = state.get("previous")
            mode = state.get("mode") or "repair"
            feedback = state.get("feedback") or ""

    if io.is_self:
        # The response must come from a later invocation. All loop state is on
        # disk, so re-entry resumes exactly here.
        raise Suspend(request.task_id, _messages(request, previous, feedback, mode), feedback)

    while index < attempts:
        io.status(
            f"  {request.task_id}: answering" if index == 0 else f"  {request.task_id}: attempt {index + 1}/{attempts}"
        )
        completion = io.call_model(_messages(request, previous, feedback, mode))
        raw, truncation = _consume(request, io, completion)
        if truncation:
            previous, mode, feedback = None, "fresh", truncation
            index += 1
            continue
        try:
            candidate, message = _validate(request, io, _prepare(request, raw))
        except ValidationFailure as exc:
            if request.mode == "proforma" and not [i for i in exc.issues if i.repair_class != "serialization"]:
                previous, mode = None, "fresh"
                feedback = _guard(request, io, state, raw, _fresh_instruction(request.task_id, str(exc)))
            else:
                previous, mode = raw, "repair"
                feedback = _guard(request, io, state, raw, _content_error(exc))
            io.record_attempt(Attempt(request.task_id, index + 1, raw, feedback))
            index += 1
            continue
        except Exception as exc:
            previous, mode = raw, "repair"
            feedback = _guard(request, io, state, raw, _content_error(exc))
            io.record_attempt(Attempt(request.task_id, index + 1, raw, feedback))
            index += 1
            continue
        io.write_output(candidate)
        io.save_state(request.task_id, {})
        return candidate
    raise TaskFailed(f"{request.task_id} failed validation after {attempts} attempt(s): {feedback}")
