"""Stable storage for declarative generic workflow artifacts."""
from __future__ import annotations

import re
from pathlib import Path

from workflows.proforma_v1 import layout


def _safe(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", str(text)).strip("_.-") or "artifact"


def generic_output_path(work: Path, step, *, create: bool = False) -> Path:
    """Return the canonical output path for a generic declarative operation."""
    fmt = str((step.output or {}).get("format") or "yaml").lower()
    ext = {"yaml": "yaml", "json": "json"}.get(fmt, "txt")
    artifact = str((step.output or {}).get("artifact") or step.id)
    group = layout.intermediate_dir(Path(work), f"workflow_{step.id}", existing=not create)
    return group / f"{_safe(artifact)}.{ext}"
