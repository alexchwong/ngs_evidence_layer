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
    validation_error: str | None = None


@dataclass(frozen=True)
class SyntaxRepairResult:
    text: str
    format_name: str
    deterministic_repairs: tuple[str, ...] = ()
    model_attempts: tuple[SyntaxRepairAttempt, ...] = ()




class SchemaSerializationRepairExhausted(ValueError):
    """A parsable artifact still violates representation-only schema constraints."""

    def __init__(
        self,
        *,
        format_name: str,
        original: str,
        candidate: str,
        validation_error: str,
        attempts: list[SyntaxRepairAttempt],
    ):
        self.format_name = format_name
        self.original = original
        self.candidate = candidate
        self.validation_error = validation_error
        self.attempts = list(attempts)
        super().__init__(
            f"{format_name.upper()} schema-serialization repair exhausted after {len(attempts)} model attempt(s): {validation_error}"
        )

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


def preservation_error(before: str, after: str, *, allow_prose_removal: bool = True) -> str | None:
    """Report any change to informational content between two artifacts.

    ``allow_prose_removal`` exists because of a failure mode that blocked runs:
    a model returns a valid document wrapped in conversational prose ("Here is
    the proforma: ... Let me know if you need anything else"), the document does
    not parse, and the syntax repairer correctly returns just the document — at
    which point a strict symmetric comparison reports the removed prose as
    *missing lexical content* and rejects the correct repair. The budget then
    burns out rejecting good answers.

    The asymmetry is safe because it is bounded on both sides:

    - nothing may be **added or changed**: any lexeme or protected token in the
      repaired artifact that was not in the original is still a hard failure;
    - nothing **protected** may be lost: IDs, numbers, percentages and card tags
      must all survive, so dropping a real value is still caught;
    - only non-protected lexemes may disappear, which is what prose is.

    Set ``allow_prose_removal=False`` for a strict comparison.
    """
    left = content_fingerprint(before)
    right = content_fingerprint(after)

    missing_protected = list((left.protected - right.protected).elements())[:12]
    added_protected = list((right.protected - left.protected).elements())[:12]
    added_lexemes = list((right.lexemes - left.lexemes).elements())[:12]
    missing_lexemes = list((left.lexemes - right.lexemes).elements())[:12]

    detail = []
    if missing_protected:
        detail.append("missing protected token(s): " + ", ".join(repr(x) for x in missing_protected))
    if added_protected:
        detail.append("added/changed protected token(s): " + ", ".join(repr(x) for x in added_protected))
    if added_lexemes:
        detail.append("added/changed lexical content: " + ", ".join(repr(x) for x in added_lexemes))
    if missing_lexemes and not allow_prose_removal:
        detail.append("missing lexical content: " + ", ".join(repr(x) for x in missing_lexemes))
    return "; ".join(detail) if detail else None


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


def schema_serialization_prompt(
    *,
    format_name: str,
    broken_text: str,
    validation_feedback: str,
    preservation_feedback: str | None = None,
    expected_schema: str | None = None,
) -> str:
    """Prompt a generic syntax model to repair parsable-but-mis-serialized data.

    Unlike :func:`repair_prompt`, the input already parses.  Only YAML/JSON
    representation may change; lexical informational content remains protected.
    """
    fmt = format_name.upper()
    lines = [
        f"Repair {fmt} serialization/shape only.",
        "The artifact already parses, but deterministic schema validation shows that some existing content was serialized into the wrong YAML/JSON type or nesting.",
        "Return only the repaired artifact.",
        "",
        "STRICT CONTENT INVARIANT:",
        "Do not add, remove, correct, reinterpret, summarise, or otherwise change informational content.",
        "Preserve every key and every scalar token exactly: diagnoses, decisions, numbers, identifiers, gene/variant text, VAFs, reasons, sources, quotes, citations, and IDs.",
        f"You may change only {fmt} representation needed to satisfy the listed serialization defects: quoting, indentation, list markers/brackets, mapping/list nesting, scalar quoting, escaping, or physical-line layout.",
        "Do NOT fix missing clinical content, invalid clinical choices, coverage gaps, unknown IDs, or semantic contradictions. Those belong to the originating task, not syntax repair.",
        "Do not add commentary.",
        "",
        "Representation-only validation defects to fix:",
        validation_feedback.strip(),
    ]
    if preservation_feedback:
        lines.extend([
            "",
            "The prior serialization-repair attempt changed informational content and was rejected:",
            preservation_feedback.strip(),
            "Repair the ORIGINAL artifact below without those content changes.",
        ])
    if expected_schema:
        lines.extend(["", "Expected serialization/shape hint:", expected_schema.strip()])
    lines.extend(["", f"Current {fmt} artifact:", broken_text.rstrip()])
    return "\n".join(lines).rstrip() + "\n"


def repair_schema_serialization(
    text: str,
    *,
    format_name: str,
    validator: Callable[[str], str],
    serialization_feedback: Callable[[Exception], str | None],
    model_repair: Callable[[str, int], str] | None = None,
    model_attempts: int = 2,
    expected_schema: str | None = None,
) -> SyntaxRepairResult:
    """Repair schema *representation* errors without changing lexical content.

    ``serialization_feedback`` returns a compact actionable error string when
    the validator exception contains one or more representation-only defects,
    otherwise ``None``.  The function stops once no representation-only defect
    remains; ordinary content/coverage validation may still fail afterwards and
    is intentionally left to the originating task.
    """
    adapter: SyntaxAdapter = adapter_for(format_name)
    candidate, deterministic_repairs = adapter.deterministic_cleanup(text)
    try:
        adapter.parse(candidate)
    except SyntaxParseError as exc:
        raise ValueError("repair_schema_serialization requires already-parsable structured text") from exc

    try:
        validator(candidate)
        return SyntaxRepairResult(
            text=candidate, format_name=adapter.name, deterministic_repairs=tuple(deterministic_repairs)
        )
    except Exception as exc:
        validation_feedback = serialization_feedback(exc)
        if not validation_feedback:
            return SyntaxRepairResult(
                text=candidate, format_name=adapter.name, deterministic_repairs=tuple(deterministic_repairs)
            )

    if model_repair is None or model_attempts <= 0:
        raise SchemaSerializationRepairExhausted(
            format_name=adapter.name, original=text, candidate=candidate,
            validation_error=validation_feedback, attempts=[]
        )

    attempts: list[SyntaxRepairAttempt] = []
    preservation_feedback: str | None = None
    original_candidate = candidate
    current = candidate
    for attempt_index in range(1, model_attempts + 1):
        prompt = schema_serialization_prompt(
            format_name=adapter.name,
            broken_text=current,
            validation_feedback=validation_feedback,
            preservation_feedback=preservation_feedback,
            expected_schema=expected_schema,
        )
        response = model_repair(prompt, attempt_index)
        cleaned, _ = adapter.deterministic_cleanup(response)
        changed = preservation_error(original_candidate, cleaned)
        if changed:
            preservation_feedback = changed
            attempts.append(SyntaxRepairAttempt(
                index=attempt_index, prompt=prompt, response=response, preservation_error=changed
            ))
            # Keep repairing from the last content-preserving artifact, not the
            # content-changing response.
            continue
        try:
            adapter.parse(cleaned)
        except SyntaxParseError as exc:
            validation_feedback = f"repair introduced parser error: {exc}"
            preservation_feedback = None
            attempts.append(SyntaxRepairAttempt(
                index=attempt_index, prompt=prompt, response=response, parser_error=str(exc)
            ))
            current = cleaned
            continue

        current = cleaned
        preservation_feedback = None
        try:
            validator(current)
        except Exception as exc:
            next_feedback = serialization_feedback(exc)
            if next_feedback:
                validation_feedback = next_feedback
                attempts.append(SyntaxRepairAttempt(
                    index=attempt_index, prompt=prompt, response=response, validation_error=next_feedback
                ))
                continue
            # Representation defects are gone.  Remaining content/schema
            # decisions intentionally flow back to the originating task.
            attempts.append(SyntaxRepairAttempt(index=attempt_index, prompt=prompt, response=response))
            return SyntaxRepairResult(
                text=current, format_name=adapter.name,
                deterministic_repairs=tuple(deterministic_repairs), model_attempts=tuple(attempts)
            )
        attempts.append(SyntaxRepairAttempt(index=attempt_index, prompt=prompt, response=response))
        return SyntaxRepairResult(
            text=current, format_name=adapter.name,
            deterministic_repairs=tuple(deterministic_repairs), model_attempts=tuple(attempts)
        )

    raise SchemaSerializationRepairExhausted(
        format_name=adapter.name, original=text, candidate=current,
        validation_error=validation_feedback, attempts=attempts
    )


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
