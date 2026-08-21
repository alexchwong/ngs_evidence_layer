"""Canonical terraced-v2 work-directory layout with compact nested shared-state folders."""
from __future__ import annotations

from pathlib import Path

DIRS = {
    "input": "input",
    "evidence": "evidence",
    "categories": "categories",
    "synthesis": "synthesis",
    "state": "state",
}


def ensure_dirs(work: Path) -> None:
    work = Path(work)
    for dirname in DIRS.values():
        (work / dirname).mkdir(parents=True, exist_ok=True)


def _nested(work: Path, group: str, name: str) -> Path:
    return Path(work) / DIRS[group] / name


def is_legacy(work: Path) -> bool:
    """True when a work directory was created by the pre-subfolder terraced layout."""
    work = Path(work)
    return (work / "terraced-run.json").is_file() and not (work / "state" / "terraced-run.json").is_file()


def artifact(work: Path, group: str, name: str, *, existing: bool = True) -> Path:
    """Return canonical nested path, with complete flat-layout resume compatibility."""
    nested = _nested(work, group, name)
    if existing and not nested.exists():
        legacy = Path(work) / name
        if legacy.exists() or is_legacy(work):
            return legacy
    return nested


def input(work: Path, name: str, *, existing: bool = True) -> Path:
    return artifact(work, "input", name, existing=existing)


def evidence(work: Path, name: str, *, existing: bool = True) -> Path:
    return artifact(work, "evidence", name, existing=existing)


def category(work: Path, name: str, *, existing: bool = True) -> Path:
    return artifact(work, "categories", name, existing=existing)


def synthesis(work: Path, name: str, *, existing: bool = True) -> Path:
    return artifact(work, "synthesis", name, existing=existing)


def state(work: Path, name: str, *, existing: bool = True) -> Path:
    return artifact(work, "state", name, existing=existing)


def model_steps(work: Path, *, existing: bool = True) -> Path:
    nested = state(work, "model-steps", existing=False)
    if existing and not nested.exists():
        legacy = Path(work) / ".model-steps"
        if legacy.exists() or is_legacy(work):
            return legacy
    return nested


def public(work: Path, name: str) -> Path:
    return Path(work) / name
