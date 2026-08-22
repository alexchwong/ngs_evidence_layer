"""Canonical terraced-v3 run-directory layout.

The run root is deliberately sparse:

- ``case.md`` and other true user inputs live at root;
- ``model_steps/`` contains the complete model-interaction audit trail;
- ``intermediates/`` contains all non-public workflow state/artifacts;
- genuine outputs (report, packages, log/manifest) live at root.

Subdirectories under ``model_steps`` and ``intermediates`` are prefixed with a
three-digit sequence allocated when that logical operation/artifact family is
first created.  Numbering is local to each namespace and reflects actual run
creation order rather than a hard-coded workflow template.
"""
from __future__ import annotations

import re
from pathlib import Path

MODEL_STEPS_DIR = "model_steps"
INTERMEDIATES_DIR = "intermediates"
_NUMBERED_RE = re.compile(r"^(\d{3})_(.+)$")


def ensure_dirs(work: Path) -> None:
    work = Path(work)
    (work / MODEL_STEPS_DIR).mkdir(parents=True, exist_ok=True)
    (work / INTERMEDIATES_DIR).mkdir(parents=True, exist_ok=True)


def _slug(text: str) -> str:
    value = "".join(ch.lower() if ch.isalnum() else "_" for ch in str(text)).strip("_")
    while "__" in value:
        value = value.replace("__", "_")
    return value or "artifact"


def _find_numbered(parent: Path, logical_name: str) -> Path | None:
    slug = _slug(logical_name)
    if not parent.is_dir():
        return None
    matches: list[tuple[int, Path]] = []
    for path in parent.iterdir():
        if not path.is_dir():
            continue
        match = _NUMBERED_RE.fullmatch(path.name)
        if match and match.group(2) == slug:
            matches.append((int(match.group(1)), path))
    if not matches:
        return None
    return sorted(matches, key=lambda item: item[0])[0][1]


def _next_number(parent: Path) -> int:
    highest = 0
    if parent.is_dir():
        for path in parent.iterdir():
            if not path.is_dir():
                continue
            match = _NUMBERED_RE.fullmatch(path.name)
            if match:
                highest = max(highest, int(match.group(1)))
    return highest + 1


def _numbered_dir(work: Path, namespace: str, logical_name: str, *, create: bool) -> Path:
    work = Path(work)
    parent = work / namespace
    if create:
        parent.mkdir(parents=True, exist_ok=True)
    existing = _find_numbered(parent, logical_name)
    if existing is not None:
        return existing
    candidate = parent / f"{_next_number(parent):03d}_{_slug(logical_name)}"
    if create:
        candidate.mkdir(parents=True, exist_ok=True)
    return candidate


def intermediate_dir(work: Path, logical_name: str, *, existing: bool = True) -> Path:
    """Return/reuse one numbered intermediate directory.

    ``existing=False`` means this operation is generating state now, so the
    directory is allocated immediately and therefore receives the next sequence
    number.  Reads use ``existing=True`` and reuse an already-created directory.
    """
    return _numbered_dir(work, INTERMEDIATES_DIR, logical_name, create=not existing)


def model_step_dir(work: Path, call_id: str, *, existing: bool = True) -> Path:
    return _numbered_dir(work, MODEL_STEPS_DIR, call_id, create=not existing)


def model_steps(work: Path, *, existing: bool = True) -> Path:
    del existing
    path = Path(work) / MODEL_STEPS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def _legacy_file(work: Path, candidates: list[Path]) -> Path | None:
    work = Path(work)
    for candidate in candidates:
        path = candidate if candidate.is_absolute() else work / candidate
        if path.exists():
            return path
    return None


def _intermediate_file(
    work: Path,
    logical_dir: str,
    name: str,
    *,
    existing: bool,
    legacy: list[Path] | None = None,
) -> Path:
    if existing:
        directory = intermediate_dir(work, logical_dir, existing=True)
        candidate = directory / name
        if candidate.exists():
            return candidate
        old = _legacy_file(work, legacy or [])
        if old is not None:
            return old
        return candidate
    directory = intermediate_dir(work, logical_dir, existing=False)
    return directory / name


def input(work: Path, name: str, *, existing: bool = True) -> Path:
    """Return a true input or setup/structured-case intermediate.

    ``case.md`` is an immutable true input and always lives at run root.
    Generated setup/configuration assets are intermediates.
    """
    work = Path(work)
    if name == "case.md":
        return work / "case.md"
    if name == "case.json":
        return _intermediate_file(
            work,
            "structured_case",
            name,
            existing=existing,
            legacy=[Path("input") / name, Path(name)],
        )
    return _intermediate_file(
        work,
        "setup",
        name,
        existing=existing,
        legacy=[Path("input") / name, Path(name)],
    )


def setup(work: Path, name: str, *, existing: bool = True) -> Path:
    return _intermediate_file(work, "setup", name, existing=existing, legacy=[Path("input") / name, Path(name)])


def _evidence_group(name: str) -> str:
    if name == "card-identity-manifest.json":
        return "card_identity"
    lowered = name.lower()
    if lowered in {"all-bundle.json", "evidence-all.md", "card-tags.json"}:
        return "combined_evidence"
    for domain in ("diagnosis", "icc", "prognosis", "treatment", "biomarker", "germline"):
        if lowered.startswith(f"{domain}-") or f"-{domain}." in lowered or f"-{domain}-" in lowered:
            return f"{domain}_evidence"
    return "evidence"


def evidence(work: Path, name: str, *, existing: bool = True) -> Path:
    return _intermediate_file(
        work,
        _evidence_group(name),
        name,
        existing=existing,
        legacy=[Path("evidence") / name, Path(name)],
    )


def _synthesis_group(name: str) -> str:
    if name.startswith("alignment-"):
        return "evidence_alignment"
    if name.startswith("fact-ledger"):
        return "fact_ledger"
    if name.startswith("report-draft") or name.startswith("sentence-fact") or name == "report-cited.md":
        return "prose_synthesis"
    return "synthesis"


def synthesis(work: Path, name: str, *, existing: bool = True) -> Path:
    return _intermediate_file(
        work,
        _synthesis_group(name),
        name,
        existing=existing,
        legacy=[Path("synthesis") / name, Path(name)],
    )


def state(work: Path, name: str, *, existing: bool = True) -> Path:
    logical = "run_state" if name == "terraced-v3-run.json" else "state"
    return _intermediate_file(
        work,
        logical,
        name,
        existing=existing,
        legacy=[Path("state") / name, Path(name)],
    )


def diagnosis(work: Path, branch: str, name: str, *, existing: bool = True) -> Path:
    branch = _slug(branch)
    return _intermediate_file(
        work,
        f"{branch}_diagnosis",
        name,
        existing=existing,
        legacy=[Path("diagnosis") / name],
    )


def diagnosis_pass_dir(work: Path, pass_name: str, *, existing: bool = True) -> Path:
    base = intermediate_dir(work, "who5_diagnosis", existing=existing)
    if existing:
        candidate = base / pass_name
        if candidate.exists():
            return candidate
        old = _legacy_file(work, [Path("diagnosis") / pass_name])
        if old is not None:
            return old
        return candidate
    base = intermediate_dir(work, "who5_diagnosis", existing=False)
    path = base / pass_name
    path.mkdir(parents=True, exist_ok=True)
    return path


def domain_dir(work: Path, domain: str, *, existing: bool = True) -> Path:
    logical = f"{_slug(domain)}_state"
    directory = intermediate_dir(work, logical, existing=existing)
    if existing and not directory.exists():
        old = _legacy_file(work, [Path(domain)])
        if old is not None:
            return old
    if not existing:
        directory = intermediate_dir(work, logical, existing=False)
    return directory


def domain(work: Path, domain_name: str, name: str, *, existing: bool = True) -> Path:
    directory = domain_dir(work, domain_name, existing=existing)
    candidate = directory / name
    if existing and candidate.exists():
        return candidate
    if existing:
        old = _legacy_file(work, [Path(domain_name) / name])
        if old is not None:
            return old
        return candidate
    directory = domain_dir(work, domain_name, existing=False)
    return directory / name


def scheduler_dir(work: Path, scheduler_id: str, *, existing: bool = True) -> Path:
    logical = f"scheduler_{_slug(scheduler_id)}"
    directory = intermediate_dir(work, logical, existing=existing)
    if existing and directory.exists():
        return directory
    if existing:
        old = _legacy_file(work, [Path("scheduler") / scheduler_id])
        if old is not None:
            return old
        return directory
    return intermediate_dir(work, logical, existing=False)


def public(work: Path, name: str) -> Path:
    return Path(work) / name
