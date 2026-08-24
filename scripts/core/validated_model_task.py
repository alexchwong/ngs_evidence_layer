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
        "clinical decisions and supplied IDs exactly. Do not troubleshoot the validator or add commentary.\n\n"
        + detail
    )
