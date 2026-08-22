"""Generic syntax-only repair for model-produced YAML and JSON.

The repairer is deliberately blind to clinical meaning. It may repair only
serialization. Every model-assisted repair is checked against a lexical content
fingerprint so changes to factual/scalar content are rejected.
"""
from __future__ import annotations

import collections
import re
from dataclasses import dataclass, field
from typing import Callable

from .adapters import SyntaxAdapter, SyntaxParseError, adapter_for

SYNTAX_REPAIR_SYSTEM_PROMPT = (
    "You are a serialization repair utility. Repair syntax only. "
    "Never add, remove, correct, reinterpret, or otherwise change informational content. "
    "Return only the repaired structured artifact."
)

# Strong invariants worth reporting separately in preservation failures.
_CARD_TAG_RE = re.compile(r"\[card:[^\]\r\n]+\]")
_PERCENT_RE = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?%")
_NUMBER_RE = re.compile(r"(?<![\w.])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?(?![\w.])")
_IDLIKE_RE = re.compile(r"\b(?=[A-Za-z0-9_.:/()+*+-]*\d)[A-Za-z][A-Za-z0-9_.:/()+*+-]{2,}\b")
# Generic lexical fingerprint: keys and scalar words/numbers must survive; YAML/
# JSON punctuation, quotation style and ordering are intentionally ignored.
_LEXEME_RE = re.compile(
    r"\[card:[^\]\r\n]+\]|"
    r"[A-Za-z0-9_]+(?:[./:+*()%-][A-Za-z0-9_]+)*|"
    r"[^\W\d_]+",
    re.UNICODE,
)


@dataclass(frozen=True)
class PreservationFingerprint:
    lexemes: collections.Counter[str]
    protected: collections.Counter[str]


@dataclass(frozen=True)
class SyntaxRepairAttempt:
    index: int
    prompt: str
    response: str
    parser_error: str | None = None
    preservation_error: str | None = None


@dataclass(frozen=True)
class SyntaxRepairResult:
    text: str
    format_name: str
    deterministic_repairs: tuple[str, ...] = ()
    model_attempts: tuple[SyntaxRepairAttempt, ...] = ()


class SyntaxRepairExhausted(ValueError):
    def __init__(
        self,
        *,
        format_name: str,
        original: str,
        candidate: str,
        parser_error: str,
        attempts: list[SyntaxRepairAttempt],
    ):
        self.format_name = format_name
        self.original = original
        self.candidate = candidate
        self.parser_error = parser_error
        self.attempts = list(attempts)
        super().__init__(
            f"{format_name.upper()} syntax repair exhausted after {len(attempts)} model attempt(s): {parser_error}"
        )


def _normalise_lexeme(token: str) -> str:
    return token.strip()


def content_fingerprint(text: str) -> PreservationFingerprint:
    lexemes = collections.Counter(
        _normalise_lexeme(token) for token in _LEXEME_RE.findall(text) if token.strip()
    )
    protected_values: list[str] = []
    for regex in (_CARD_TAG_RE, _PERCENT_RE, _IDLIKE_RE, _NUMBER_RE):
        protected_values.extend(regex.findall(text))
    return PreservationFingerprint(
        lexemes=lexemes,
        protected=collections.Counter(protected_values),
    )


def preservation_error(before: str, after: str) -> str | None:
    left = content_fingerprint(before)
    right = content_fingerprint(after)
    if left.protected != right.protected:
        missing = list((left.protected - right.protected).elements())[:12]
        added = list((right.protected - left.protected).elements())[:12]
        detail = []
        if missing:
            detail.append("missing protected token(s): " + ", ".join(repr(x) for x in missing))
        if added:
            detail.append("added/changed protected token(s): " + ", ".join(repr(x) for x in added))
        return "; ".join(detail)
    if left.lexemes != right.lexemes:
        missing = list((left.lexemes - right.lexemes).elements())[:12]
        added = list((right.lexemes - left.lexemes).elements())[:12]
        detail = []
        if missing:
            detail.append("missing lexical content: " + ", ".join(repr(x) for x in missing))
        if added:
            detail.append("added/changed lexical content: " + ", ".join(repr(x) for x in added))
        return "; ".join(detail)
    return None


def repair_prompt(
    *,
    format_name: str,
    broken_text: str,
    parser_error: str,
    preservation_feedback: str | None = None,
    expected_schema: str | None = None,
) -> str:
    fmt = format_name.upper()
    lines = [
        f"Repair {fmt} syntax only.",
        "Return only the repaired artifact.",
        "",
        "STRICT CONTENT INVARIANT:",
        "Do not add, remove, correct, reinterpret, summarise, or otherwise change any fact or informational content.",
        "Preserve every key, scalar value, diagnosis, decision, number, identifier, gene/variant text, VAF, reason, citation, and ID exactly.",
        f"You may change only {fmt} serialization needed to make the document parse, such as indentation, quoting, list/object delimiters, colons, commas, escaping, or brackets.",
        "Do not improve the answer. Do not resolve contradictions. Do not add commentary.",
        "",
        "Parser error:",
        parser_error.strip(),
    ]
    if preservation_feedback:
        lines.extend([
            "",
            "The prior syntax-repair attempt changed content and was rejected:",
            preservation_feedback.strip(),
            "Repair the ORIGINAL artifact below without making those changes.",
        ])
    if expected_schema:
        lines.extend(["", "Expected serialization/shape hint:", expected_schema.strip()])
    lines.extend(["", f"Broken {fmt} artifact:", broken_text.rstrip()])
    return "\n".join(lines).rstrip() + "\n"


def reserialization_prompt(
    *,
    format_name: str,
    broken_text: str,
    parser_error: str,
    expected_schema: str | None = None,
) -> str:
    fmt = format_name.upper()
    lines = [
        f"Your previous answer could not be made syntactically valid {fmt}.",
        f"Return the SAME factual answer as one syntactically valid {fmt} artifact only.",
        "Do not reconsider the clinical task and do not add, remove, correct, reinterpret, or change any fact, decision, number, identifier, reason, citation, or ID.",
        "Change serialization only. Do not add commentary.",
        "",
        "Parser problem:",
        parser_error.strip(),
    ]
    if expected_schema:
        lines.extend(["", "Expected serialization/shape hint:", expected_schema.strip()])
    lines.extend(["", "Previous artifact:", broken_text.rstrip()])
    return "\n".join(lines).rstrip() + "\n"


def repair_structured_output(
    text: str,
    *,
    format_name: str,
    model_repair: Callable[[str, int], str] | None = None,
    model_attempts: int = 2,
    expected_schema: str | None = None,
) -> SyntaxRepairResult:
    """Return parsable YAML/JSON while preserving lexical informational content.

    `model_repair` receives a compact syntax-only prompt and a 1-based syntax
    attempt number. It must return only a candidate repaired artifact.
    """
    adapter: SyntaxAdapter = adapter_for(format_name)
    candidate, deterministic_repairs = adapter.deterministic_cleanup(text)
    try:
        adapter.parse(candidate)
        return SyntaxRepairResult(
            text=candidate,
            format_name=adapter.name,
            deterministic_repairs=tuple(deterministic_repairs),
        )
    except SyntaxParseError as initial_error:
        parser_error = str(initial_error)

    attempts: list[SyntaxRepairAttempt] = []
    if model_repair is None or model_attempts <= 0:
        raise SyntaxRepairExhausted(
            format_name=adapter.name,
            original=text,
            candidate=candidate,
            parser_error=parser_error,
            attempts=attempts,
        )

    preservation_feedback: str | None = None
    for attempt_index in range(1, model_attempts + 1):
        prompt = repair_prompt(
            format_name=adapter.name,
            broken_text=candidate,
            parser_error=parser_error,
            preservation_feedback=preservation_feedback,
            expected_schema=expected_schema,
        )
        response = model_repair(prompt, attempt_index)
        cleaned, _ = adapter.deterministic_cleanup(response)
        changed = preservation_error(candidate, cleaned)
        if changed:
            preservation_feedback = changed
            attempts.append(SyntaxRepairAttempt(
                index=attempt_index,
                prompt=prompt,
                response=response,
                preservation_error=changed,
            ))
            continue
        try:
            adapter.parse(cleaned)
        except SyntaxParseError as exc:
            parser_error = str(exc)
            preservation_feedback = None
            attempts.append(SyntaxRepairAttempt(
                index=attempt_index,
                prompt=prompt,
                response=response,
                parser_error=parser_error,
            ))
            continue
        attempts.append(SyntaxRepairAttempt(index=attempt_index, prompt=prompt, response=response))
        return SyntaxRepairResult(
            text=cleaned,
            format_name=adapter.name,
            deterministic_repairs=tuple(deterministic_repairs),
            model_attempts=tuple(attempts),
        )

    raise SyntaxRepairExhausted(
        format_name=adapter.name,
        original=text,
        candidate=candidate,
        parser_error=parser_error,
        attempts=attempts,
    )
