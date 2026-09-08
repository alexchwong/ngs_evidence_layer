"""Runtime prompt composition for proforma-v1.

Static includes retain their existing behavior.  The default workflow may also
use named, versioned ``module`` directives whose enable/version selection comes
from ``configs/default/*.yaml``.
"""
from __future__ import annotations
import re
from pathlib import Path

from workflows.proforma_v1 import default_config

_INCLUDE_RE = re.compile(r'^\s*\{\{\s*include\s+["\']([^"\']+)["\']\s*\}\}\s*$', re.MULTILINE)
_MODULE_RE = re.compile(r'^\s*\{\{\s*module\s+["\']([A-Za-z0-9._-]+)["\']\s*\}\}\s*$', re.MULTILINE)


class PromptIncludeError(ValueError):
    pass


def _package_root(root: Path) -> Path:
    root = root.resolve()
    if root.name == "prompts":
        return root.parent
    if (root / "prompts").is_dir():
        return root
    return root.parent if (root.parent / "prompts").is_dir() else root


def _render_module(name: str, *, root: Path, stack: tuple[Path, ...]) -> str:
    try:
        spec = default_config.module_spec(name)
    except ValueError as exc:
        raise PromptIncludeError(str(exc)) from exc
    if not spec["enabled"]:
        return default_config.BLANK_SECTION
    package = _package_root(root)
    child = package / "prompts" / "modules" / name / f"{spec['version']}.md"
    if not child.is_file():
        raise PromptIncludeError(
            f"prompt module asset not found for {name!r} version {spec['version']!r}: {child}"
        )
    return render(child, root=package, _stack=stack).rstrip()


def render(path: Path, *, root: Path, _stack: tuple[Path, ...] = ()) -> str:
    root = root.resolve()
    path = (path if path.is_absolute() else root / path).resolve()
    package = _package_root(root)
    allowed_roots = {root, package}
    if not any(_is_relative_to(path, candidate) for candidate in allowed_roots):
        raise PromptIncludeError(f'prompt include escapes prompt root: {path}')
    if path in _stack:
        chain = ' -> '.join(p.name for p in (*_stack, path))
        raise PromptIncludeError(f'prompt include cycle: {chain}')
    if not path.is_file():
        raise PromptIncludeError(f'prompt asset not found: {path}')
    text = path.read_text(encoding='utf-8')
    stack = (*_stack, path)

    def include_repl(match: re.Match[str]) -> str:
        child = (path.parent / match.group(1)).resolve()
        if not any(_is_relative_to(child, candidate) for candidate in allowed_roots):
            raise PromptIncludeError(f'prompt include escapes prompt root: {child}')
        return render(child, root=root, _stack=stack).rstrip()

    text = _INCLUDE_RE.sub(include_repl, text)
    text = _MODULE_RE.sub(
        lambda match: "\n" + _render_module(match.group(1), root=root, stack=stack) + "\n", text
    )
    return text.rstrip() + '\n'


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False
