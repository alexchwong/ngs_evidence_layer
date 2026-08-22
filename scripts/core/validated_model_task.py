"""Workflow-neutral structural validation and repair support for model tasks.

YAML/JSON syntax repair lives in `scripts.core.syntax_repair`. This module retains
lightweight cleanup for non-structured text plus workflow-neutral structured
validation issues and ordinary task-retry instructions. It never changes clinical
content. Workflow/task validators remain responsible for semantic invariants.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
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


@dataclass
class RetryStagnationGuard:
    """Detect repeated byte-equivalent invalid candidates with the same failure.

    The first repeat is allowed but gets explicit feedback.  A second consecutive
    repeat means the task model is not responding to the validator and the caller
    should stop rather than spend the remainder of its retry budget.
    """

    last_key: str | None = None
    repeats: int = 0

    def observe(self, candidate: str, error_text: str) -> int:
        key = hashlib.sha256((candidate + "\0" + error_text).encode("utf-8")).hexdigest()
        if key == self.last_key:
            self.repeats += 1
        else:
            self.last_key = key
            self.repeats = 0
        return self.repeats


def stagnation_instruction(repeat_count: int) -> str:
    return (
        "\n\nThe last invalid artifact was byte-identical to the prior invalid artifact. "
        f"This is repeated invalid output #{repeat_count}. Do not repeat it again; "
        "make the specific serialization or validation correction requested above while preserving unrelated content."
    )


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
