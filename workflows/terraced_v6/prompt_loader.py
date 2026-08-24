"""Runtime prompt composition for terraced-v6.

Prompt assets can inject other prompt assets with a line such as:

    {{ include "includes/audit_general.md" }}

Includes are resolved relative to the workflow prompt root, recursively, with
cycle and path-escape protection.  This keeps shared policy in editable prompt
assets instead of Python.
"""
from __future__ import annotations
import re
from pathlib import Path

_INCLUDE_RE = re.compile(r'^\s*\{\{\s*include\s+["\']([^"\']+)["\']\s*\}\}\s*$', re.MULTILINE)

class PromptIncludeError(ValueError):
    pass

def render(path: Path, *, root: Path, _stack: tuple[Path, ...] = ()) -> str:
    root = root.resolve()
    path = (path if path.is_absolute() else root / path).resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise PromptIncludeError(f'prompt include escapes prompt root: {path}') from exc
    if path in _stack:
        chain = ' -> '.join(p.name for p in (*_stack, path))
        raise PromptIncludeError(f'prompt include cycle: {chain}')
    if not path.is_file():
        raise PromptIncludeError(f'prompt asset not found: {path}')
    text = path.read_text(encoding='utf-8')
    stack = (*_stack, path)
    def repl(match: re.Match[str]) -> str:
        child = (path.parent / match.group(1)).resolve()
        try:
            child.relative_to(root)
        except ValueError as exc:
            raise PromptIncludeError(f'prompt include escapes prompt root: {child}') from exc
        return render(child, root=root, _stack=stack).rstrip()
    return _INCLUDE_RE.sub(repl, text).rstrip() + '\n'
