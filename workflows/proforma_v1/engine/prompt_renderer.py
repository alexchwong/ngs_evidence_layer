"""Static prompt includes plus declared runtime placeholders.

The renderer intentionally supports only ``{{ input.NAME }}`` and
``{{ output.template }}`` runtime placeholders. Includes remain delegated to
``prompt_loader`` so Phase 1 prompt bytes are unchanged when no placeholders are
present.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import yaml

from workflows.proforma_v1 import prompt_loader

_PLACEHOLDER = re.compile(r"\{\{\s*(input\.[A-Za-z_][A-Za-z0-9_]*|output\.template)\s*\}\}")
_ANY_TEMPLATE = re.compile(r"\{\{.*?\}\}", re.DOTALL)


class PromptRenderError(ValueError):
    pass


def placeholders(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(m.group(1) for m in _PLACEHOLDER.finditer(text)))


def validate_placeholders(text: str, declared_inputs: set[str]) -> tuple[str, ...]:
    known = {f"input.{name}" for name in declared_inputs} | {"output.template"}
    found = placeholders(text)
    unknown = sorted(set(found) - known)
    if unknown:
        raise PromptRenderError(f"undeclared runtime placeholder(s): {unknown}")
    residual = []
    for m in _ANY_TEMPLATE.finditer(text):
        token = m.group(0)
        if not _PLACEHOLDER.fullmatch(token):
            residual.append(" ".join(token.split()))
    if residual:
        raise PromptRenderError(f"unsupported prompt template expression(s): {residual}")
    return found


def compile_asset(path: Path, *, root: Path, declared_inputs: set[str]) -> str:
    text = prompt_loader.render(path, root=root)
    validate_placeholders(text, declared_inputs)
    return text


def _render_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list, tuple)):
        return yaml.safe_dump(value, sort_keys=False, allow_unicode=True, width=110).rstrip()
    if value is None:
        return "null"
    if isinstance(value, (bool, int, float)):
        return json.dumps(value)
    return str(value)


def render(path: Path, *, root: Path, inputs: dict[str, Any], output_template: Any = "") -> str:
    text = compile_asset(path, root=root, declared_inputs=set(inputs))
    values = {f"input.{key}": value for key, value in inputs.items()}
    values["output.template"] = output_template

    def repl(match: re.Match[str]) -> str:
        return _render_value(values[match.group(1)])

    return _PLACEHOLDER.sub(repl, text)
