"""Format adapters for generic structured-output syntax repair."""
from __future__ import annotations

import json
import re
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

    trailing = "\n".join(line.rstrip() for line in candidate.strip().splitlines())
    candidate = trailing + ("\n" if trailing else "")
    if candidate != text and not repairs:
        repairs.append("normalised surrounding/trailing whitespace")
    return candidate, repairs


_YAML_MAPPING_LINE_RE = re.compile(r"^(?P<indent>\s*(?:-\s+)?)" r"(?P<key>[A-Za-z_][A-Za-z0-9_.-]*):(?P<space>\s+)(?P<value>.+)$")

def _repair_yaml_plain_scalar_colon(candidate: str) -> tuple[str, list[str]]:
    """Quote parser-identified YAML plain scalars containing ``: ``.

    This is representation-only: the complete scalar text is preserved byte-for-byte
    after YAML decoding.  The repair is attempted only when PyYAML reports the
    specific ``mapping values are not allowed here`` error and the offending line
    has a simple ``key: scalar`` shape.  Any resulting structure is still subject to
    the caller's ordinary task/schema validator.
    """
    repairs: list[str] = []
    # More than a handful of such failures in one artifact usually indicates a
    # different structural problem; keep the deterministic rescue deliberately
    # bounded.
    for _ in range(12):
        try:
            yaml.safe_load(candidate)
            return candidate, repairs
        except yaml.YAMLError as exc:
            problem = (getattr(exc, "problem", None) or "").strip().lower()
            mark = getattr(exc, "problem_mark", None)
            if problem != "mapping values are not allowed here" or mark is None:
                return candidate, repairs
            lines = candidate.splitlines()
            if mark.line < 0 or mark.line >= len(lines):
                return candidate, repairs
            line = lines[mark.line]
            match = _YAML_MAPPING_LINE_RE.match(line)
            if not match:
                return candidate, repairs
            value = match.group("value")
            # Already-explicit YAML scalars/collections should not be rewritten.
            if not value or value[0] in "\"'|>[{&*!?%@`":
                return candidate, repairs
            # The parser mark must point to a colon-space sequence inside the value,
            # not the key/value delimiter itself.
            value_start = match.start("value")
            relative = mark.column - value_start
            if relative < 0 or relative >= len(value) or value[relative:relative + 2] != ": ":
                return candidate, repairs
            quoted = json.dumps(value, ensure_ascii=False)
            lines[mark.line] = line[:value_start] + quoted
            candidate = "\n".join(lines) + ("\n" if candidate.endswith("\n") else "")
            repairs.append(f"quoted YAML plain scalar on line {mark.line + 1} containing ': '")
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
        candidate, scalar_repairs = _repair_yaml_plain_scalar_colon(candidate)
        repairs.extend(scalar_repairs)
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
