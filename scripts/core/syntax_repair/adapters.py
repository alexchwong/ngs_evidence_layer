"""Format adapters for generic structured-output syntax repair."""
from __future__ import annotations

import json
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


# A line that plausibly belongs to a YAML/JSON document rather than to prose.
_STRUCTURAL_RE = __import__("re").compile(
    r"""^\s*(?:
          [-#]                       # list item or comment
        | [\[\]{}]                   # JSON punctuation
        | ["']?[\w.$/-]+["']?\s*:    # a mapping key
        | \|                         # block scalar continuation
        | >                          #  "
    )""",
    __import__("re").VERBOSE,
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


def _common_cleanup(text: str) -> tuple[str, list[str]]:
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
        candidate, repairs = _common_cleanup(text)
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
            import json as _json
            import re as _re

            scalar_line = _re.compile(
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
                    quoted_lines.append(match.group("prefix") + _json.dumps(value))
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
        return candidate, repairs


class JsonSyntaxAdapter:
    name = "json"

    def parse(self, text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise SyntaxParseError("JSON", exc.msg, exc.lineno, exc.colno) from exc

    def deterministic_cleanup(self, text: str) -> tuple[str, list[str]]:
        return _common_cleanup(text)


def adapter_for(format_name: str) -> SyntaxAdapter:
    key = format_name.strip().lower()
    if key in {"yaml", "yml"}:
        return YamlSyntaxAdapter()
    if key == "json":
        return JsonSyntaxAdapter()
    raise ValueError(f"unsupported structured syntax format {format_name!r}; expected yaml or json")
