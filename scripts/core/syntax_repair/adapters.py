"""Format adapters for generic structured-output syntax repair."""
from __future__ import annotations

import json
import re
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any, Protocol

import yaml


@dataclass(frozen=True)
class SyntaxParseError(ValueError):
    format_name: str
    message: str
    line: int | None = None
    column: int | None = None

    def __str__(self) -> str:
        where = ""
        if self.line is not None:
            where = f" at line {self.line}"
            if self.column is not None:
                where += f", column {self.column}"
        return f"{self.format_name} parser error{where}: {self.message}"


class WrongStructuredArtifactError(ValueError):
    """The model returned a document of the wrong kind, not damaged YAML/JSON.

    This is intentionally distinct from :class:`SyntaxParseError`: converting a
    Markdown reasoning document into a schema mapping would require adding,
    deleting and reorganising informational content, which a syntax-only repair
    model is forbidden to do.  Callers should return this failure to the
    originating model instead of consuming the syntax-repair budget.
    """

    def __init__(self, format_name: str, reason: str):
        self.format_name = str(format_name).upper()
        self.reason = str(reason)
        super().__init__(
            f"wrong artifact type for {self.format_name}: {self.reason}. "
            f"Regenerate the complete answer as the required single {self.format_name} artifact; "
            "do not ask syntax repair to convert a prose/Markdown document into the schema."
        )




_REPAIR_OBSERVER: ContextVar[Any] = ContextVar("syntax_repair_observer", default=None)
_CLASSIFY_WRONG_ARTIFACT: ContextVar[bool] = ContextVar("classify_wrong_structured_artifact", default=False)


@contextmanager
def classify_wrong_artifacts():
    """Enable wrong-artifact classification for one reasoning output boundary."""
    token = _CLASSIFY_WRONG_ARTIFACT.set(True)
    try:
        yield
    finally:
        _CLASSIFY_WRONG_ARTIFACT.reset(token)


@contextmanager
def observe_deterministic_repairs(callback):
    """Observe deterministic cleanup performed inside one bounded caller context.

    The hook is opt-in and context-local so shared/default workflows are unchanged.
    Reasoning provider execution uses it to persist cleanup that occurs inside the
    generic model runner before the reasoning executor can inspect the artifact.
    """
    token = _REPAIR_OBSERVER.set(callback)
    try:
        yield
    finally:
        _REPAIR_OBSERVER.reset(token)


def _emit_repairs(repairs: list[str]) -> None:
    callback = _REPAIR_OBSERVER.get()
    if callback is not None and repairs:
        callback(tuple(repairs))


class SyntaxAdapter(Protocol):
    name: str

    def parse(self, text: str) -> Any: ...

    def deterministic_cleanup(self, text: str) -> tuple[str, list[str]]: ...


def _fenced_block(text: str) -> str | None:
    """Return the contents of the first fenced block, if the text contains one.

    The previous rule only fired when a fence wrapped the *entire* response, so
    the very common "Here is the YAML: ```yaml ...``` Let me know if..." shape
    was left with its prose attached — which made the artifact unparsable and,
    worse, made a correct repair look like content loss to the preservation
    check.
    """
    lines = text.splitlines()
    opens = [i for i, line in enumerate(lines) if line.lstrip().startswith("```")]
    if len(opens) < 2:
        return None
    start, end = opens[0], opens[1]
    if end <= start + 1:
        return None
    return "\n".join(lines[start + 1 : end])


_MD_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+\S", re.MULTILINE)
_MD_TABLE_SEPARATOR_RE = re.compile(
    r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$",
    re.MULTILINE,
)
_MD_DOCUMENT_SEPARATOR_RE = re.compile(r"^ {0,3}---\s*$", re.MULTILINE)


def wrong_artifact_reason(text: str) -> str | None:
    """Return a conservative reason when ``text`` is clearly a Markdown document.

    A single ``# comment`` is legal YAML and is therefore never sufficient.
    We require unmistakable document structure: Markdown subsection headings,
    or a Markdown table associated with headings.  Fenced structured output is
    excluded because deterministic cleanup can safely extract the fenced block.
    """
    raw = str(text or "")
    if not raw.strip() or _fenced_block(raw) is not None:
        return None
    headings = list(_MD_HEADING_RE.finditer(raw))
    subheadings = [match for match in headings if len(match.group(1)) >= 2]
    if len(subheadings) >= 1 and len(headings) >= 2:
        return "the response is a multi-section Markdown document rather than one structured mapping"
    if headings and _MD_TABLE_SEPARATOR_RE.search(raw):
        return "the response contains a Markdown table/document rather than one structured mapping"
    separators = list(_MD_DOCUMENT_SEPARATOR_RE.finditer(raw))
    if subheadings and separators:
        return "the response uses Markdown document sections/separators rather than one structured mapping"
    # A document separator in the middle of otherwise mapping-like material is
    # also not a local YAML syntax defect: it represents more than one document.
    # Do not classify a leading YAML ``---`` document marker this way.
    mapping_line = re.compile(r"^\s*[\"']?[A-Za-z_][A-Za-z0-9_.-]*[\"']?\s*:", re.MULTILINE)
    for separator in separators:
        before = raw[: separator.start()]
        after = raw[separator.end() :]
        if mapping_line.search(before) and mapping_line.search(after):
            return "the response contains multiple document sections rather than one structured mapping"
    return None


# A line that plausibly belongs to a YAML/JSON document rather than to prose.
_STRUCTURAL_RE = re.compile(
    r"""^\s*(?:
          [-#]                       # list item or comment
        | [\[\]{}]                   # JSON punctuation
        | ["']?[\w.$/-]+["']?\s*:    # a mapping key
        | \|                         # block scalar continuation
        | >                          #  "
    )""",
    re.VERBOSE,
)


def _strip_surrounding_prose(text: str) -> tuple[str, bool]:
    """Trim leading/trailing non-structural lines around a structured document.

    Conservative: it only trims at the ends, never in the middle, and only when
    at least one structural line remains. Continuation lines of multi-line
    scalars are indented, so trimming from the outside in cannot orphan them.
    """
    lines = text.splitlines()
    idx = [i for i, line in enumerate(lines) if line.strip() and _STRUCTURAL_RE.match(line)]
    if not idx:
        return text, False
    first, last = idx[0], idx[-1]
    # Keep indented continuation lines that follow the last structural line.
    while last + 1 < len(lines) and lines[last + 1].startswith((" ", "\t")) and lines[last + 1].strip():
        last += 1
    if first == 0 and last == len(lines) - 1:
        return text, False
    return "\n".join(lines[first : last + 1]), True


def _common_cleanup(text: str, *, format_name: str) -> tuple[str, list[str]]:
    """Apply only representation-only cleanup shared by structured formats."""
    repairs: list[str] = []
    candidate = text

    if candidate.startswith("\ufeff"):
        candidate = candidate.lstrip("\ufeff")
        repairs.append("removed UTF-8 BOM")

    normalised = candidate.replace("\r\n", "\n").replace("\r", "\n")
    if normalised != candidate:
        candidate = normalised
        repairs.append("normalised line endings")

    stripped = candidate.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if len(lines) >= 2 and lines[-1].strip() == "```":
            candidate = "\n".join(lines[1:-1])
            repairs.append("removed surrounding Markdown code fence")
    if "```" in candidate:
        block = _fenced_block(candidate)
        if block is not None:
            candidate = block
            repairs.append("extracted the fenced code block from surrounding prose")

    # After any safely extractable fenced block has been handled, a wholesale
    # Markdown document is not a syntax-repair problem.  Raise before parser
    # repair so the originating model receives contract feedback instead.
    reason = wrong_artifact_reason(candidate) if _CLASSIFY_WRONG_ARTIFACT.get() else None
    if reason:
        _emit_repairs(repairs)
        raise WrongStructuredArtifactError(format_name, reason)

    if candidate.strip():
        trimmed, did = _strip_surrounding_prose(candidate)
        if did:
            candidate = trimmed
            repairs.append("removed prose surrounding the structured document")

    trailing = "\n".join(line.rstrip() for line in candidate.strip().splitlines())
    candidate = trailing + ("\n" if trailing else "")
    if candidate != text and not repairs:
        repairs.append("normalised surrounding/trailing whitespace")
    return candidate, repairs


class YamlSyntaxAdapter:
    name = "yaml"

    def parse(self, text: str) -> Any:
        try:
            return yaml.safe_load(text)
        except yaml.YAMLError as exc:
            mark = getattr(exc, "problem_mark", None)
            line = mark.line + 1 if mark is not None else None
            column = mark.column + 1 if mark is not None else None
            problem = getattr(exc, "problem", None) or str(exc)
            raise SyntaxParseError("YAML", problem, line, column) from exc

    def deterministic_cleanup(self, text: str) -> tuple[str, list[str]]:
        candidate, repairs = _common_cleanup(text, format_name=self.name)
        # YAML forbids tabs for indentation. Expanding leading indentation tabs
        # preserves the model's apparent nesting intent without touching scalar tabs.
        lines: list[str] = []
        expanded = False
        for line in candidate.splitlines():
            prefix_len = len(line) - len(line.lstrip("\t "))
            prefix = line[:prefix_len]
            if "\t" in prefix:
                prefix = prefix.expandtabs(2)
                expanded = True
            lines.append(prefix + line[prefix_len:])
        if expanded:
            candidate = "\n".join(lines) + ("\n" if candidate else "")
            repairs.append("expanded indentation tabs to spaces")

        # A common model serialization error is an unquoted plain-text mapping
        # scalar containing ``: `` (for example ``reason: Case fact C2: 30%``).
        # YAML interprets the second colon as another mapping delimiter.  Quoting
        # the complete value is representation-only when the line is otherwise a
        # simple key/value mapping, so repair that narrow form deterministically.
        try:
            self.parse(candidate)
        except SyntaxParseError:
            scalar_line = re.compile(
                r"^(?P<prefix>\s*(?:-\s+)?[^:#\n][^:\n]*:\s*)"
                r"(?P<value>[^\n]+)$"
            )
            quoted_lines: list[str] = []
            quoted_any = False
            for line in candidate.splitlines():
                match = scalar_line.match(line)
                if not match:
                    quoted_lines.append(line)
                    continue
                value = match.group("value")
                stripped = value.strip()
                if (
                    ": " in value
                    and stripped
                    and stripped[0] not in "'\"[{>|&*!"
                ):
                    quoted_lines.append(match.group("prefix") + json.dumps(value))
                    quoted_any = True
                else:
                    quoted_lines.append(line)
            if quoted_any:
                repaired = "\n".join(quoted_lines) + ("\n" if candidate.endswith("\n") else "")
                try:
                    self.parse(repaired)
                except SyntaxParseError:
                    pass
                else:
                    candidate = repaired
                    repairs.append("quoted YAML plain scalar containing colon-space")
        _emit_repairs(repairs)
        return candidate, repairs


class JsonSyntaxAdapter:
    name = "json"

    def parse(self, text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise SyntaxParseError("JSON", exc.msg, exc.lineno, exc.colno) from exc

    def deterministic_cleanup(self, text: str) -> tuple[str, list[str]]:
        candidate, repairs = _common_cleanup(text, format_name=self.name)
        _emit_repairs(repairs)
        return candidate, repairs


def adapter_for(format_name: str) -> SyntaxAdapter:
    key = format_name.strip().lower()
    if key in {"yaml", "yml"}:
        return YamlSyntaxAdapter()
    if key == "json":
        return JsonSyntaxAdapter()
    raise ValueError(f"unsupported structured syntax format {format_name!r}; expected yaml or json")
