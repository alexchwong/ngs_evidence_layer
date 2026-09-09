"""Workflow-neutral structural validation and repair support for model tasks.

Repair is deliberately split into three functional layers:
1. serialization repair for representation-only defects;
2. schema-preserving repair for shape/contract defects that must not change meaning;
3. content repair for validation failures that require the task context and a substantive decision.

Workflow/task validators remain responsible for domain invariants.  The routing in this
module does not make clinical judgments.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable
from collections import Counter
import hashlib
import json
import re

import yaml


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    problem: str
    required_fix: str
    repair_class: str = "content"
    received: str | None = None
    expected: str | None = None

    def render(self, index: int) -> str:
        lines = [f"{index}. {self.path}", f"   Problem: {self.problem}.", f"   Required fix: {self.required_fix}."]
        if self.received is not None:
            lines.append(f"   Received: {self.received}")
        if self.expected is not None:
            lines.append(f"   Expected: {self.expected}")
        return "\n".join(lines)


MAX_RENDERED_ISSUES = 8
SCHEMA_REPAIR_CLASSES = frozenset({"schema_preserving"})


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
    def __init__(self, context: str, issues: list[ValidationIssue]):
        self.context = context
        self.issues = list(issues)
        super().__init__(f"{context} failed validation with {len(self.issues)} issue(s):\n" + render_issues(self.issues))


def fail(context: str, issues: list[ValidationIssue]) -> None:
    if issues:
        raise ValidationFailure(context, issues)


def safe_representation_repair(text: str) -> tuple[str, list[str]]:
    original = text
    stripped = text.strip()
    repairs: list[str] = []
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            stripped = "\n".join(lines[1:-1])
            repairs.append("removed surrounding Markdown code fence")
    cleaned = "\n".join(line.rstrip() for line in stripped.splitlines()).strip()
    cleaned = cleaned + "\n" if cleaned else ""
    if cleaned != original and not repairs:
        repairs.append("normalised surrounding/trailing whitespace")
    return cleaned, repairs


def validate_with_safe_repair(raw_text: str, validator: Callable[[str], str]) -> tuple[str, str, list[str]]:
    candidate, repairs = safe_representation_repair(raw_text)
    return candidate, validator(candidate), repairs


class RetryStagnationGuard:
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
    if repeat_count <= 0:
        return ""
    return (
        "\n\nThe last repair repeated the same invalid artifact and validation error. "
        "Make a material correction to the stated validation issue; do not return the same artifact again."
    )


def retry_instruction(error: Exception) -> str:
    detail = str(error).strip() or type(error).__name__
    return (
        "The previous complete artifact failed deterministic validation. Return the complete artifact again, not a patch. "
        "Fix every issue below and preserve unrelated decisions and supplied IDs exactly. "
        "Do not troubleshoot the validator or add commentary.\n\n" + detail
    )


class Truncated:
    def __init__(self, content: str, *, max_tokens: int):
        self.content = content
        self.max_tokens = max_tokens


class TaskFailed(RuntimeError):
    """A task exhausted its budget, or stopped early because it was stagnating."""


class TaskContractError(RuntimeError):
    """Deterministic preparation contradicted a stated validator contract."""


class Suspend(Exception):
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
    schema: int = 1


@dataclass(frozen=True)
class TaskRequest:
    task_id: str
    messages: list[dict]
    validate: Callable[[str], str]
    budgets: Budgets
    fmt: str | None = None
    mode: str = "standard"
    prepare: Callable[[str], str] | None = None


@dataclass(frozen=True)
class TaskIO:
    call_model: Callable[[list[dict]], Any]
    load_state: Callable[[str], dict]
    save_state: Callable[[str, dict], None]
    read_output: Callable[[], str | None]
    write_output: Callable[[str], None]
    call_syntax_model: Callable[[str, int], str] | None = None
    call_schema_model: Callable[[str, int], str] | None = None
    call_content_model: Callable[[list[dict], int], Any] | None = None
    record_attempt: Callable[[Any], None] = lambda attempt: None
    record_syntax_attempt: Callable[[Any], None] = lambda attempt: None
    record_schema_attempt: Callable[[Any], None] = lambda attempt: None
    record_content_attempt: Callable[[Any], None] = lambda attempt: None
    status: Callable[[str], None] = lambda message: None
    is_self: bool = False


@dataclass
class Attempt:
    task_id: str
    index: int
    response: str
    error: str | None = None


@dataclass
class SyntaxAttempt(Attempt):
    pass


@dataclass
class SchemaAttempt(Attempt):
    pass


@dataclass
class ContentAttempt(Attempt):
    pass


STAGNATION_ABORT_AFTER = 2


def _fingerprint(text: str) -> str:
    return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()[:16]


def _issues(error: Exception, classes: set[str] | frozenset[str] | None = None, *, exclude: set[str] | frozenset[str] = frozenset()) -> list[ValidationIssue]:
    if not isinstance(error, ValidationFailure):
        return []
    rows = error.issues
    if classes is not None:
        rows = [i for i in rows if i.repair_class in classes]
    if exclude:
        rows = [i for i in rows if i.repair_class not in exclude]
    return rows


def _serialization_issues(error: Exception) -> list[ValidationIssue]:
    return _issues(error, {"serialization"})


def _schema_issues(error: Exception) -> list[ValidationIssue]:
    return _issues(error, SCHEMA_REPAIR_CLASSES)


def _content_issues(error: Exception) -> list[ValidationIssue]:
    return _issues(error, exclude={"serialization", *SCHEMA_REPAIR_CLASSES})


def _content_error(error: Exception) -> str:
    if isinstance(error, ValidationFailure):
        content = _content_issues(error)
        if content:
            return retry_instruction(ValidationFailure(error.context, content))
    return retry_instruction(error)


def _fresh_instruction(task_id: str, detail: str) -> str:
    return (
        "The previous complete artifact could not be made structurally valid. Regenerate the complete artifact from scratch "
        "from the original task and supplied context. Do not copy, patch, or troubleshoot the previous artifact. "
        "The structural problem was:\n\n" + str(detail).strip()
    )


def _truncation_instruction(max_tokens: int) -> str:
    return f"The previous answer was truncated at max_tokens={max_tokens}. Return the complete artifact again from scratch, not a patch or a continuation."


class _PreparedText(str):
    def __new__(cls, value: str, raw_before_prepare: str):
        obj = str.__new__(cls, value)
        obj.raw_before_prepare = str(raw_before_prepare)
        return obj


def _prepare(request: TaskRequest, raw: str) -> str:
    prepared = request.prepare(raw) if request.prepare else raw
    if prepared == raw:
        return prepared
    return _PreparedText(prepared, raw)


_REQUIRED_FIELD_PATTERNS = (
    re.compile(r"\bmissing(?:\s+required)?(?:\s+field)?\s+[`'\"]?([A-Za-z_][A-Za-z0-9_]*)", re.I),
    re.compile(r"[`'\"]([A-Za-z_][A-Za-z0-9_]*)[`'\"]\s+is\s+a\s+required\s+property", re.I),
    re.compile(r"\brequired\s+(?:field|key)\s+[`'\"]?([A-Za-z_][A-Za-z0-9_]*)", re.I),
)


def _key_occurs(text: str, key: str) -> bool:
    return bool(re.search(rf"(?m)^\s*(?:-\s+)?[\"']?{re.escape(key)}[\"']?\s*:", str(text or "")))


def _prepare_contract_error(candidate: str, error: Exception) -> str | None:
    raw = getattr(candidate, "raw_before_prepare", None)
    if raw is None:
        return None
    names: list[str] = []
    for pattern in _REQUIRED_FIELD_PATTERNS:
        names.extend(pattern.findall(str(error)))
    for key in dict.fromkeys(names):
        if _key_occurs(raw, key) and not _key_occurs(candidate, key):
            return (
                f"workflow_contract_error: deterministic preparation removed required field {key!r} that was present in the model candidate, "
                "then validation reported it missing. Do not retry the model; repair the transform/schema ownership contract."
            )
    return None


def _validate_once(request: TaskRequest, candidate: str) -> str:
    try:
        return request.validate(candidate)
    except Exception as exc:
        contradiction = _prepare_contract_error(candidate, exc)
        if contradiction:
            raise TaskContractError(contradiction) from exc
        raise


def _scalar_signature(text: str, fmt: str | None) -> Counter:
    """Key-insensitive scalar multiset used to police model-assisted schema repair.

    A schema-repair model may rename/move/wrap existing values, but it may not add,
    delete, or rewrite informational scalar values.  Deterministic canonicalization
    handles the small allow-list of exceptions such as rendered-card-tag extraction.
    """
    name = str(fmt or "").lower()
    try:
        if name == "json":
            doc = json.loads(str(text))
        elif name in {"yaml", "yml"}:
            doc = yaml.safe_load(str(text))
        else:
            return Counter()
    except Exception:
        return Counter()
    values: list[str] = []
    def walk(value):
        if isinstance(value, dict):
            for child in value.values():
                walk(child)
        elif isinstance(value, list):
            for child in value:
                walk(child)
        else:
            values.append(repr(value))
    walk(doc)
    return Counter(values)


def _schema_prompt(error: ValidationFailure, artifact: str) -> str:
    return (
        "Repair schema/shape only. Preserve every clinical fact, conclusion, enum choice, reason, supplied ID, and evidence assignment exactly. "
        "Do not invent missing informational content. Return the complete artifact only.\n\n"
        "Schema/shape defects to fix:\n" + render_issues(_schema_issues(error)) + "\n\nCurrent artifact:\n" + artifact
    )


def _content_messages(request: TaskRequest, error: Exception, artifact: str) -> list[dict]:
    feedback = (
        "The previous complete artifact failed deterministic validation. Re-evaluate only the rejected issues using the original task, case, evidence, "
        "and instructions above. Return the complete artifact, not a patch. Preserve unrelated clinical decisions and supplied IDs exactly. "
        "Do not discuss or troubleshoot the validator.\n\n" + _content_error(error)
    )
    return list(request.messages) + [{"role": "assistant", "content": artifact}, {"role": "user", "content": feedback}]


def _repair_validation(request: TaskRequest, io: TaskIO, candidate: str) -> tuple[str, str]:
    """Validate and route failures through serialization -> schema -> content repair."""
    current = candidate
    try:
        return current, _validate_once(request, current)
    except ValidationFailure as exc:
        error: Exception = exc

    # Serialization-only defects are handled first. If a repair reveals a schema/content
    # defect, routing falls through without sending it back to the syntax model.
    serial_attempt = 0
    while _serialization_issues(error) and io.call_syntax_model is not None and serial_attempt < request.budgets.serialization:
        serial_attempt += 1
        prompt = (
            "Repair serialization only. Do not add, remove, or change informational content.\n\nRepresentation-only defects to fix:\n"
            + render_issues(_serialization_issues(error)) + "\n\nCurrent artifact:\n" + current
        )
        io.status(f"  {request.task_id}: serialization repair {serial_attempt}/{request.budgets.serialization}")
        current = _prepare(request, io.call_syntax_model(prompt, serial_attempt))
        try:
            message = _validate_once(request, current)
        except Exception as exc:
            error = exc
            io.record_syntax_attempt(SyntaxAttempt(request.task_id, serial_attempt, current, str(exc)))
        else:
            io.record_syntax_attempt(SyntaxAttempt(request.task_id, serial_attempt, current))
            return current, message

    if isinstance(error, ValidationFailure) and _schema_issues(error) and io.call_schema_model is not None:
        for attempt in range(1, request.budgets.schema + 1):
            io.status(f"  {request.task_id}: schema-preserving repair {attempt}/{request.budgets.schema}")
            before = current
            before_signature = _scalar_signature(before, request.fmt)
            current = _prepare(request, io.call_schema_model(_schema_prompt(error, current), attempt))
            after_signature = _scalar_signature(current, request.fmt)
            if before_signature and after_signature != before_signature:
                error = ValidationFailure(request.task_id, [ValidationIssue(
                    path="$",
                    problem="schema-preserving repair changed informational scalar values",
                    required_fix="preserve all existing scalar values exactly and change only schema/shape",
                    repair_class="schema_preserving",
                )])
                io.record_schema_attempt(SchemaAttempt(request.task_id, attempt, current, str(error)))
                current = before
                continue
            try:
                message = _validate_once(request, current)
            except Exception as exc:
                error = exc
                io.record_schema_attempt(SchemaAttempt(request.task_id, attempt, current, str(exc)))
                if not isinstance(exc, ValidationFailure) or not _schema_issues(exc):
                    break
            else:
                io.record_schema_attempt(SchemaAttempt(request.task_id, attempt, current))
                return current, message

    content_needed = not isinstance(error, ValidationFailure) or bool(_content_issues(error))
    if io.call_content_model is not None and content_needed:
        attempts = max(1, request.budgets.rewrite if request.mode == "proforma" else request.budgets.content)
        guard = RetryStagnationGuard()
        for attempt in range(1, attempts + 1):
            io.status(f"  {request.task_id}: content repair {attempt}/{attempts}")
            completion = io.call_content_model(_content_messages(request, error, current), attempt)
            raw, truncation = _consume(request, io, completion)
            if truncation:
                error = RuntimeError(truncation)
                current = raw
                continue
            current = _prepare(request, raw)
            try:
                message = _validate_once(request, current)
            except Exception as exc:
                error = exc
                io.record_content_attempt(ContentAttempt(request.task_id, attempt, current, str(exc)))
                if guard.observe(current, str(exc)) >= STAGNATION_ABORT_AFTER:
                    break
            else:
                io.record_content_attempt(ContentAttempt(request.task_id, attempt, current))
                return current, message

    if isinstance(error, ValidationFailure):
        raise error
    raise error


def _validate(request: TaskRequest, io: TaskIO, candidate: str) -> tuple[str, str]:
    # New routed behavior is opt-in through the repair callbacks. Legacy callers retain
    # the prior serialization-only helper and owner retry semantics.
    if io.call_schema_model is not None or io.call_content_model is not None:
        return _repair_validation(request, io, candidate)
    try:
        return candidate, _validate_once(request, candidate)
    except ValidationFailure as exc:
        serial = _serialization_issues(exc)
        if not serial or io.call_syntax_model is None or request.budgets.serialization <= 0:
            raise
    repaired = candidate
    for attempt in range(1, request.budgets.serialization + 1):
        prompt = (
            "Repair serialization only. Do not add, remove, or change informational content.\n\nRepresentation-only defects to fix:\n"
            + render_issues(serial) + "\n\nCurrent artifact:\n" + repaired
        )
        io.status(f"  {request.task_id}: serialization repair {attempt}/{request.budgets.serialization}")
        repaired = _prepare(request, io.call_syntax_model(prompt, attempt))
        try:
            message = _validate_once(request, repaired)
        except ValidationFailure as exc:
            serial = _serialization_issues(exc)
            io.record_syntax_attempt(SyntaxAttempt(request.task_id, attempt, repaired, str(exc)))
            if not serial:
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
        raise TaskFailed(f"{request.task_id} returned the same rejected artifact and the same error {repeats + 1} times; stopping early rather than retrying unchanged. Last feedback:\n{feedback}")
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
    if isinstance(completion, Truncated):
        return completion.content, _truncation_instruction(completion.max_tokens)
    return getattr(completion, "content", completion), None


def run(request: TaskRequest, io: TaskIO) -> str:
    state = io.load_state(request.task_id)
    attempts = request.budgets.rewrite + 1 if request.mode == "proforma" else request.budgets.content
    index = int(state.get("rewrites", 0))
    mode = state.get("mode") or "initial"
    feedback = state.get("feedback") or ""
    previous = state.get("previous")
    routed = io.call_schema_model is not None or io.call_content_model is not None

    existing = io.read_output()
    if existing is not None:
        existing_fp = _fingerprint(existing)
        if state.get("consumed_output_fingerprint") != existing_fp:
            try:
                candidate, _ = _validate(request, io, _prepare(request, existing))
            except TaskContractError:
                raise
            except Exception as exc:
                if routed:
                    raise TaskFailed(f"{request.task_id} repair routing failed for existing output: {exc}") from exc
                feedback = _guard(request, io, state, existing, _content_error(exc))
                previous, mode, index = existing, "repair", index + 1
                state.update({"rewrites": index, "mode": mode, "feedback": feedback, "previous": previous, "consumed_output_fingerprint": existing_fp})
                io.save_state(request.task_id, state)
                io.record_attempt(Attempt(request.task_id, index, existing, feedback))
                if index >= attempts:
                    raise TaskFailed(f"{request.task_id} failed validation after {attempts} attempt(s): {feedback}")
            else:
                io.write_output(candidate)
                io.save_state(request.task_id, {})
                return candidate
        else:
            previous = state.get("previous")
            mode = state.get("mode") or "repair"
            feedback = state.get("feedback") or ""

    if io.is_self:
        raise Suspend(request.task_id, _messages(request, previous, feedback, mode), feedback)

    while index < attempts:
        completion = io.call_model(_messages(request, previous, feedback, mode))
        raw, truncation = _consume(request, io, completion)
        if truncation:
            previous, mode, feedback = None, "fresh", truncation
            index += 1
            continue
        try:
            candidate, _ = _validate(request, io, _prepare(request, raw))
        except TaskContractError:
            raise
        except Exception as exc:
            if routed:
                io.record_attempt(Attempt(request.task_id, index + 1, raw, str(exc)))
                raise TaskFailed(f"{request.task_id} repair routing failed after owner output: {exc}") from exc
            if isinstance(exc, ValidationFailure) and request.mode == "proforma" and not [i for i in exc.issues if i.repair_class != "serialization"]:
                previous, mode = None, "fresh"
                feedback = _guard(request, io, state, raw, _fresh_instruction(request.task_id, str(exc)))
            else:
                previous, mode = raw, "repair"
                feedback = _guard(request, io, state, raw, _content_error(exc))
            io.record_attempt(Attempt(request.task_id, index + 1, raw, feedback))
            index += 1
            continue
        io.write_output(candidate)
        io.save_state(request.task_id, {})
        return candidate
    raise TaskFailed(f"{request.task_id} failed validation after {attempts} attempt(s): {feedback}")
