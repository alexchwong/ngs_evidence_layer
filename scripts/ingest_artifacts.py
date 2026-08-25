#!/usr/bin/env python3
"""Filename conventions and compatibility resolvers for ingestion phase artefacts."""
import json
import re
from pathlib import Path

CENSUS_NEW_RE = re.compile(r"^paper\.census-v(?P<attempt>[0-9]{3})\.json$")
CENSUS_LEGACY = "paper.census.json"
PROVISIONAL_NEW_RE = re.compile(
    r"^paper\.provisional(?:-rev(?P<revision>[0-9]{3}))?-v(?P<attempt>[0-9]{3})\.json$"
)
PROVISIONAL_LEGACY_RE = re.compile(r"^paper\.provisional-(?P<attempt>[0-9]{3})\.json$")
REVIEW_NEW_RE = re.compile(
    r"^paper\.review(?:-rev(?P<revision>[0-9]{3}))?-v(?P<attempt>[0-9]{3})\.json$"
)
REVIEW_LEGACY_RE = re.compile(r"^paper\.review-(?P<attempt>[0-9]{3})\.json$")
PHASE2_STATE_RE = re.compile(r"^paper\.phase2-state-v(?P<attempt>[0-9]{3})\.json$")
PHASE2R_DECISION_RE = re.compile(
    r"^paper\.phase2r-decisions(?:-rev(?P<revision>[0-9]{3}))?-v(?P<attempt>[0-9]{3})\.json$"
)
PHASE4_DECISION_RE = re.compile(
    r"^paper\.phase4-decisions(?:-rev(?P<revision>[0-9]{3}))?-v(?P<attempt>[0-9]{3})\.json$"
)


def _read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def census_name(attempt):
    return f"paper.census-v{attempt:03d}.json"


def phase2_state_name(census_attempt_number):
    return f"paper.phase2-state-v{census_attempt_number:03d}.json"


def phase2_state_attempt(path):
    match = PHASE2_STATE_RE.fullmatch(Path(path).name)
    return int(match.group("attempt")) if match else None


def resolve_phase2_state_for_census(folder, census_path):
    """Resolve the checkpoint tied exactly to a census attempt, if present."""
    attempt = census_attempt(census_path)
    if attempt is None:
        return None
    path = Path(folder) / phase2_state_name(attempt)
    return path if path.is_file() else None


def provisional_name(attempt, revision=None):
    if revision is None:
        return f"paper.provisional-v{attempt:03d}.json"
    return f"paper.provisional-rev{revision:03d}-v{attempt:03d}.json"


def review_name(attempt, revision=None):
    if revision is None:
        return f"paper.review-v{attempt:03d}.json"
    return f"paper.review-rev{revision:03d}-v{attempt:03d}.json"




def decision_name(stage, attempt, revision=None):
    if stage not in {"phase2r", "phase4"}:
        raise ValueError("decision stage must be phase2r or phase4")
    prefix = f"paper.{stage}-decisions"
    if revision is not None:
        prefix += f"-rev{revision:03d}"
    return f"{prefix}-v{attempt:03d}.json"


def decision_identity(path, stage):
    name = Path(path).name
    pattern = PHASE2R_DECISION_RE if stage == "phase2r" else PHASE4_DECISION_RE if stage == "phase4" else None
    if pattern is None:
        raise ValueError("decision stage must be phase2r or phase4")
    match = pattern.fullmatch(name)
    if not match:
        return None
    revision = match.group("revision")
    return (int(revision) if revision else None, int(match.group("attempt")))


def resolve_decision_for_attempt(folder, stage, attempt, revision=None):
    folder = Path(folder)
    if not folder.is_dir():
        return None
    expected = decision_name(stage, attempt, revision=revision)
    path = folder / expected
    return path if path.is_file() else None

def census_attempt(path):
    name = Path(path).name
    if name == CENSUS_LEGACY:
        return 1
    match = CENSUS_NEW_RE.fullmatch(name)
    return int(match.group("attempt")) if match else None


def _phase_identity(path, *, kind):
    name = Path(path).name
    if kind == "provisional":
        match = PROVISIONAL_NEW_RE.fullmatch(name)
        if match:
            revision = match.group("revision")
            return (int(revision) if revision else None, int(match.group("attempt")), False)
        match = PROVISIONAL_LEGACY_RE.fullmatch(name)
        if match:
            return (None, int(match.group("attempt")), True)
    elif kind == "review":
        match = REVIEW_NEW_RE.fullmatch(name)
        if match:
            revision = match.group("revision")
            return (int(revision) if revision else None, int(match.group("attempt")), False)
        match = REVIEW_LEGACY_RE.fullmatch(name)
        if match:
            return (None, int(match.group("attempt")), True)
    return None


def phase_identity(path, kind):
    """Return (revision, attempt) for a provisional/review filename, or None."""
    identity = _phase_identity(path, kind=kind)
    return identity[:2] if identity else None


def next_census_attempt(folder):
    attempts = [
        attempt
        for path in Path(folder).iterdir()
        if path.is_file() and (attempt := census_attempt(path)) is not None
    ] if Path(folder).is_dir() else []
    return max(attempts + [0]) + 1


def next_phase_attempt(folder, kind, revision=None):
    attempts = []
    folder = Path(folder)
    if folder.is_dir():
        for path in folder.iterdir():
            if not path.is_file():
                continue
            identity = _phase_identity(path, kind=kind)
            if identity and identity[0] == revision:
                attempts.append(identity[1])
    return max(attempts + [0]) + 1


def resolve_census(folder):
    """Resolve the newest census; legacy paper.census.json counts as v001."""
    folder = Path(folder)
    candidates = []
    if not folder.is_dir():
        return None
    for path in folder.iterdir():
        if not path.is_file():
            continue
        attempt = census_attempt(path)
        if attempt is not None:
            # Prefer explicit v001 over legacy only if both somehow exist.
            candidates.append((attempt, path.name != CENSUS_LEGACY, path))
    return max(candidates, default=(None, None, None))[2]


def _phase_candidates(folder, kind, revision=None):
    folder = Path(folder)
    candidates = []
    if not folder.is_dir():
        return candidates
    for path in folder.iterdir():
        if not path.is_file():
            continue
        identity = _phase_identity(path, kind=kind)
        if not identity or identity[0] != revision:
            continue
        candidates.append((identity[1], not identity[2], path))
    return sorted(candidates)


def resolve_phase_for_round(folder, kind, round_number, revision=None):
    """Resolve the best lineage candidate for a requested internal round.

    Prefer a file whose JSON declares the round. Legacy/malformed artefacts are still
    returned by filename so the downstream validator can emit the specific mismatch
    instead of incorrectly reporting the file as absent.
    """
    candidates = _phase_candidates(folder, kind, revision=revision)
    matches = []
    for attempt, explicit, path in candidates:
        document = _read_json(path)
        if isinstance(document, dict) and document.get("round") == round_number:
            matches.append((attempt, explicit, path))
    if matches:
        return max(matches)[2]
    same_attempt = [item for item in candidates if item[0] == round_number]
    if same_attempt:
        return max(same_attempt)[2]
    return max(candidates, default=(None, None, None))[2]


def resolve_phase_any_revision_for_round(folder, kind, round_number):
    """Resolve a unique namespace for a round, preferring the newest attempt within it."""
    folder = Path(folder)
    namespaces = {}
    if not folder.is_dir():
        return None
    revisions = {None}
    for path in folder.iterdir():
        identity = _phase_identity(path, kind=kind) if path.is_file() else None
        if identity:
            revisions.add(identity[0])
    for revision in revisions:
        path = resolve_phase_for_round(folder, kind, round_number, revision=revision)
        if path is not None:
            namespaces[revision] = path
    if len(namespaces) == 1:
        return next(iter(namespaces.values()))
    if not namespaces:
        return None
    raise ValueError(
        f"multiple {kind} namespaces contain round {round_number}; cannot resolve lineage: "
        + ", ".join(str(path.name) for path in namespaces.values())
    )


def max_revision(folder):
    folder = Path(folder)
    revisions = []
    if not folder.is_dir():
        return 0
    for path in folder.iterdir():
        if not path.is_file():
            continue
        for kind in ("provisional", "review"):
            identity = _phase_identity(path, kind=kind)
            if identity and identity[0] is not None:
                revisions.append(identity[0])
    return max(revisions + [0])
