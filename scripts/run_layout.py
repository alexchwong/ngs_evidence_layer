"""Authoritative run/batch filesystem layout for the root NEL facade.

A valid top-level run contains ``run.json``. A valid top-level batch contains
``batch.json`` and each declared child contains its own ``run.json``. Logical
run references never become filesystem paths: nested children use
``<batch-id>:<case-id>`` and both components are validated independently.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
RUN_MANIFEST = "run.json"
BATCH_MANIFEST = "batch.json"
BATCH_STATE = "batch-state.json"
BATCH_SOURCE = "batch-source.md"
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
CASE_HEADING_RE = re.compile(r"(?m)^# Case(?:[ \t]+[^\n]+)?[ \t]*$", re.IGNORECASE)
STRICT_CASE_HEADING_RE = re.compile(r"^# Case[ \t]+(.+?)[ \t]*$", re.IGNORECASE)


class LayoutError(ValueError):
    pass


@dataclass(frozen=True)
class RunLocation:
    run_id: str
    path: Path
    manifest: dict[str, Any]
    batch_id: str | None = None
    case_id: str | None = None

    @property
    def is_batch_child(self) -> bool:
        return self.batch_id is not None


@dataclass(frozen=True)
class BatchLocation:
    batch_id: str
    path: Path
    manifest: dict[str, Any]


@dataclass(frozen=True)
class ParsedCase:
    title: str
    case_id: str
    text: str


def validate_id(value: Any, *, label: str = "identifier") -> str:
    text = str(value or "").strip()
    if not text:
        raise LayoutError(f"{label} is required")
    if text in {".", "..", "LATEST"} or not ID_RE.fullmatch(text):
        raise LayoutError(
            f"invalid {label}; use only letters, numbers, '.', '_' and '-', "
            "and start with a letter or number"
        )
    return text


def slug(value: str) -> str:
    text = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-._")
    return text or "case"


def split_run_ref(run_ref: Any) -> tuple[str | None, str]:
    text = str(run_ref or "").strip()
    if not text:
        raise LayoutError("run identifier is required")
    if text.count(":") > 1:
        raise LayoutError("invalid run identifier: batch child references use <batch-id>:<case-id>")
    if ":" not in text:
        return None, validate_id(text, label="run ID")
    batch_id, case_id = text.split(":", 1)
    return validate_id(batch_id, label="batch ID"), validate_id(case_id, label="case ID")


def child_run_ref(batch_id: str, case_id: str) -> str:
    return f"{validate_id(batch_id, label='batch ID')}:{validate_id(case_id, label='case ID')}"


def _read_object(path: Path, *, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LayoutError(f"{label} is missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LayoutError(f"invalid JSON in {label} {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LayoutError(f"{label} must contain a JSON object: {path}")
    return value


def _write_object(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".tmp-{os.getpid()}")
    tmp.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def write_run_manifest(
    path: Path,
    *,
    run_id: str,
    workflow: str,
    mode: str,
    pipeline: str,
    created_at: str,
    batch_id: str | None = None,
    case_id: str | None = None,
    case_title: str | None = None,
) -> dict[str, Any]:
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "kind": "run",
        "run_id": str(run_id),
        "workflow": str(workflow),
        "mode": str(mode),
        "pipeline": str(pipeline),
        "created_at": str(created_at),
    }
    if batch_id is not None:
        manifest["batch_id"] = validate_id(batch_id, label="batch ID")
    if case_id is not None:
        manifest["case_id"] = validate_id(case_id, label="case ID")
    if case_title:
        manifest["case_title"] = str(case_title)
    _write_object(Path(path) / RUN_MANIFEST, manifest)
    return manifest


def load_run_manifest(path: Path) -> dict[str, Any]:
    manifest = _read_object(Path(path) / RUN_MANIFEST, label="run manifest")
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("kind") != "run":
        raise LayoutError(f"unsupported run manifest schema: {Path(path) / RUN_MANIFEST}")
    if not isinstance(manifest.get("run_id"), str) or not manifest["run_id"].strip():
        raise LayoutError(f"run manifest has no run_id: {Path(path) / RUN_MANIFEST}")
    return manifest


def load_batch(path: Path) -> BatchLocation:
    path = Path(path)
    manifest = _read_object(path / BATCH_MANIFEST, label="batch manifest")
    if manifest.get("schema_version") != SCHEMA_VERSION or manifest.get("kind") != "batch":
        raise LayoutError(f"unsupported batch manifest schema: {path / BATCH_MANIFEST}")
    batch_id = validate_id(manifest.get("batch_id"), label="batch ID")
    if path.name != batch_id:
        raise LayoutError(
            f"batch manifest ID {batch_id!r} does not match its folder name {path.name!r}"
        )
    children = manifest.get("children")
    if not isinstance(children, list):
        raise LayoutError(f"batch manifest children must be a list: {path / BATCH_MANIFEST}")
    seen: set[str] = set()
    for row in children:
        if not isinstance(row, dict):
            raise LayoutError("batch manifest child entries must be objects")
        case_id = validate_id(row.get("case_id"), label="case ID")
        if case_id in seen:
            raise LayoutError(f"batch manifest defines case {case_id!r} more than once")
        seen.add(case_id)
        expected_ref = child_run_ref(batch_id, case_id)
        if row.get("run_id") != expected_ref:
            raise LayoutError(
                f"batch child {case_id!r} has run_id {row.get('run_id')!r}; expected {expected_ref!r}"
            )
    return BatchLocation(batch_id=batch_id, path=path, manifest=manifest)


def resolve_batch(runs_root: Path, batch_id: Any) -> BatchLocation:
    batch_id = validate_id(batch_id, label="batch ID")
    path = Path(runs_root) / batch_id
    if not path.is_dir():
        raise LayoutError(f"batch not found: {batch_id}")
    if not (path / BATCH_MANIFEST).is_file():
        if (path / RUN_MANIFEST).is_file():
            raise LayoutError(f"{batch_id} is a single run, not a batch")
        raise LayoutError(
            f"unsupported legacy run layout: {batch_id} has no {BATCH_MANIFEST} or {RUN_MANIFEST}"
        )
    return load_batch(path)


def _declared_child(batch: BatchLocation, case_id: str) -> dict[str, Any]:
    for row in batch.manifest.get("children", []):
        if isinstance(row, dict) and row.get("case_id") == case_id:
            return row
    raise LayoutError(f"batch {batch.batch_id} does not contain case {case_id}")


def resolve_run(runs_root: Path, run_ref: Any) -> RunLocation:
    runs_root = Path(runs_root)
    batch_id, run_id_or_case = split_run_ref(run_ref)
    if batch_id is None:
        path = runs_root / run_id_or_case
        if not path.is_dir():
            raise LayoutError(f"run not found: {run_id_or_case}")
        if (path / BATCH_MANIFEST).is_file():
            raise LayoutError(
                f"{run_id_or_case} is a batch; use 'nel.py batch run --run-id {run_id_or_case}'"
            )
        if not (path / RUN_MANIFEST).is_file():
            raise LayoutError(
                f"unsupported legacy run layout: {run_id_or_case} is missing {RUN_MANIFEST}"
            )
        manifest = load_run_manifest(path)
        if manifest.get("batch_id"):
            raise LayoutError(f"batch child is stored at the top level: {run_id_or_case}")
        if manifest.get("run_id") != run_id_or_case:
            raise LayoutError(
                f"run manifest ID {manifest.get('run_id')!r} does not match folder {run_id_or_case!r}"
            )
        return RunLocation(run_id=run_id_or_case, path=path, manifest=manifest)

    batch = resolve_batch(runs_root, batch_id)
    case_id = validate_id(run_id_or_case, label="case ID")
    child = _declared_child(batch, case_id)
    path = batch.path / case_id
    if not path.is_dir():
        raise LayoutError(f"batch child folder is missing: {batch_id}:{case_id}")
    manifest = load_run_manifest(path)
    expected_ref = child_run_ref(batch_id, case_id)
    if manifest.get("run_id") != expected_ref:
        raise LayoutError(
            f"child run manifest ID {manifest.get('run_id')!r} does not match {expected_ref!r}"
        )
    if manifest.get("batch_id") != batch_id or manifest.get("case_id") != case_id:
        raise LayoutError(f"child run manifest parent relationship is invalid: {expected_ref}")
    if child.get("run_id") != expected_ref:
        raise LayoutError(f"batch manifest membership is invalid for {expected_ref}")
    return RunLocation(
        run_id=expected_ref,
        path=path,
        manifest=manifest,
        batch_id=batch_id,
        case_id=case_id,
    )


def classify_top_level(path: Path) -> str:
    path = Path(path)
    has_run = (path / RUN_MANIFEST).is_file()
    has_batch = (path / BATCH_MANIFEST).is_file()
    if has_run and has_batch:
        return "invalid"
    if has_run:
        return "run"
    if has_batch:
        return "batch"
    return "unsupported"


def iter_top_level(runs_root: Path) -> Iterable[tuple[str, Path]]:
    root = Path(runs_root)
    if not root.is_dir():
        return ()
    return tuple(
        (classify_top_level(path), path)
        for path in sorted(root.iterdir(), key=lambda p: p.name.lower())
        if path.is_dir()
    )


def parse_case_markdown(text: str) -> list[ParsedCase]:
    """Split strict ``# Case <title>`` input, with deterministic errors.

    Only H1 headings beginning exactly with ``# Case `` delimit cases. Any
    non-whitespace before the first case heading is an error. Empty cases and
    duplicate titles are rejected rather than silently repaired.
    """
    raw = str(text or "")
    if not raw.strip():
        raise LayoutError("batch case input is empty; start each case with '# Case <title>'")

    matches = list(CASE_HEADING_RE.finditer(raw))
    if not matches:
        raise LayoutError(
            "batch case format error: no '# Case <title>' headings were found; "
            "each case must start with a Markdown H1 such as '# Case 1'"
        )
    prefix = raw[: matches[0].start()]
    if prefix.strip():
        raise LayoutError(
            "batch case format error: content appears before the first '# Case <title>' heading"
        )

    parsed: list[ParsedCase] = []
    seen_titles: set[str] = set()
    seen_ids: set[str] = set()
    for index, match in enumerate(matches):
        heading = match.group(0).strip()
        strict = STRICT_CASE_HEADING_RE.fullmatch(heading)
        if strict is None or not strict.group(1).strip():
            line_no = raw.count("\n", 0, match.start()) + 1
            raise LayoutError(
                f"batch case format error on line {line_no}: use '# Case <title>' with a non-empty title"
            )
        title = strict.group(1).strip()
        key = title.casefold()
        if key in seen_titles:
            raise LayoutError(f"batch case format error: duplicate case title {title!r}")
        seen_titles.add(key)
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        body = raw[body_start:body_end].strip()
        if not body:
            raise LayoutError(f"batch case format error: '# Case {title}' has no case text")
        base_id = f"{index + 1:03d}-{slug(title).lower()}"
        case_id = base_id
        suffix = 2
        while case_id in seen_ids:
            case_id = f"{base_id}-{suffix}"
            suffix += 1
        seen_ids.add(case_id)
        case_text = f"# Case {title}\n\n{body}\n"
        parsed.append(ParsedCase(title=title, case_id=case_id, text=case_text))
    return parsed


def parse_case_ids(value: Any) -> list[str]:
    text = str(value or "").strip()
    if not text:
        raise LayoutError("validation batch requires --case-ids <id1,id2,...>")
    parts = [part.strip() for part in text.split(",")]
    if any(not part for part in parts):
        raise LayoutError("--case-ids must be a comma-delimited list with no empty entries")
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        # Validation selectors are source identifiers, not path components. Keep
        # their existing character flexibility but forbid separators/control text.
        if any(ch in part for ch in ("/", "\\", ":")) or part in {".", ".."}:
            raise LayoutError(f"invalid validation case ID: {part!r}")
        if part in seen:
            raise LayoutError(f"duplicate validation case ID: {part!r}")
        seen.add(part)
        out.append(part)
    return out


def initial_batch_state(children: list[dict[str, Any]], *, created_at: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "prepared",
        "created_at": created_at,
        "started_at": None,
        "finished_at": None,
        "stopped_at": None,
        "children": {
            str(row["case_id"]): {
                "status": "prepared",
                "attempt_count": 0,
                "last_exit_code": None,
                "last_failure_stage": None,
                "last_started_at": None,
                "last_finished_at": None,
            }
            for row in children
        },
    }


def load_batch_state(batch: BatchLocation) -> dict[str, Any]:
    path = batch.path / BATCH_STATE
    if not path.is_file():
        return initial_batch_state(batch.manifest.get("children", []), created_at=str(batch.manifest.get("created_at") or ""))
    state = _read_object(path, label="batch state")
    if state.get("schema_version") != SCHEMA_VERSION:
        raise LayoutError(f"unsupported batch state schema: {path}")
    if not isinstance(state.get("children"), dict):
        raise LayoutError(f"batch state children must be an object: {path}")
    return state


def write_batch_state(batch: BatchLocation | Path, state: dict[str, Any]) -> None:
    path = batch.path if isinstance(batch, BatchLocation) else Path(batch)
    _write_object(path / BATCH_STATE, state)


def write_batch_manifest(path: Path, manifest: dict[str, Any]) -> None:
    _write_object(Path(path) / BATCH_MANIFEST, manifest)
