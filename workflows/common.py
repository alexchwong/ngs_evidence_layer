"""Shared deterministic workflow utilities.

Workflow strategy stays in each workflow package. This module contains only
mechanical helpers that are intentionally identical between workflows.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = REPO_ROOT / "scripts"
CASE_MAJOR_CATEGORY_INSTRUCTION = (
    "Select exactly one case_major_category representing the supplied starting "
    "clinicomorphological major category; do not revise it using molecular results."
)


def resolve_work_dir(path: Path | None, *, project: bool = False) -> Path:
    if path is not None:
        work = Path(path).expanduser().resolve()
        if work.exists() and not work.is_dir():
            raise ValueError(f"work directory path exists but is not a directory: {work}")
        work.mkdir(parents=True, exist_ok=True)
    else:
        root = None
        if project:
            root = REPO_ROOT / "temp"
            root.mkdir(exist_ok=True)
        work = Path(tempfile.mkdtemp(prefix="ngs-evidence-layer-", dir=root)).resolve()

    probe = work / ".workflow_writable"
    try:
        probe.write_text("", encoding="utf-8")
        probe.unlink()
    except OSError as exc:
        raise ValueError(f"work directory is not writable: {work}") from exc
    return work


def announce(work_dir: Path) -> None:
    print(f"[run_case] working directory: {work_dir}", file=sys.stderr)


def run_command(command: list[str], stage: str) -> None:
    print(f"[run_case] {stage}", file=sys.stderr)
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"{stage} failed: {exc}") from exc
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"{stage} failed: interpreter or script not found: {exc}"
        ) from exc


def require_file(path: Path, description: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"expected output not produced: {description} ({path})")


def remove_if_present(*paths: Path) -> None:
    for path in paths:
        if path.exists():
            path.unlink()


def write_case_major_categories(output: Path, categories: list[str] | tuple[str, ...]) -> Path:
    payload = {
        "case_major_categories": list(categories),
        "instruction": CASE_MAJOR_CATEGORY_INSTRUCTION,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output
