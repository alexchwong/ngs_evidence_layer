"""Workflow-neutral structural validation and repair support for model tasks.

YAML/JSON syntax repair lives in `scripts.core.syntax_repair`. This module retains
lightweight cleanup for non-structured text plus workflow-neutral structured
validation issues and ordinary task-retry instructions. It never changes clinical
content. Workflow/task validators remain responsible for semantic invariants.
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
        parts = [
            f"{index}. {self.path} — Problem: {self.problem}.",
            f"Required fix: {self.required_fix}.",
        ]
        if self.received is not None:
            parts.append(f"Received: {self.received}.")
        if self.expected is not None:
            parts.append(f"Expected: {self.expected}.")
        return " ".join(parts)


class ValidationFailure(ValueError):
    """A model-fixable validation failure with structured actionable issues."""

    def __init__(self, context: str, issues: list[ValidationIssue]):
        self.context = context
        self.issues = list(issues)
        rendered = "\n".join(issue.render(i) for i, issue in enumerate(self.issues, 1))
        super().__init__(
            f"{context} failed validation with {len(self.issues)} issue(s):\n{rendered}"
        )


def fail(context: str, issues: list[ValidationIssue]) -> None:
    if issues:
        raise ValidationFailure(context, issues)


def safe_representation_repair(text: str) -> tuple[str, list[str]]:
    """Apply only serialization-preserving cleanup with no clinical judgement."""
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
    resets the count.  Callers can use this to stop wasting clinical retries on
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


def retry_instruction(error: Exception) -> str:
    """Render one complete, self-contained repair request for the next model attempt."""
    if isinstance(error, ValidationFailure):
        detail = str(error)
    else:
        detail = str(error).strip() or type(error).__name__
    return (
        "The previous complete artifact failed deterministic validation. "
        "Return the complete artifact again, not a patch. Fix every issue below and preserve unrelated "
        "clinical decisions and supplied IDs exactly. Do not troubleshoot the validator or add commentary.\n\n"
        + detail
    )
