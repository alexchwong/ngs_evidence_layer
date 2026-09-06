"""Persistent, workflow-neutral filesystem records for proforma-v1 model calls."""
from __future__ import annotations

import json
import os
import tempfile
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA_VERSION = 1
INDEX_NAME = "model-operations.json"

# One logical model task can be re-entered after a semantic review invalidates
# its canonical artifact. The shared task runner numbers attempts from 1 on each
# re-entry, so keep a process-local map from those logical attempt numbers to
# append-only physical attempt directories. Historical attempt directories are
# never overwritten.
_ACTIVE_ATTEMPT_MAP: dict[tuple[str, int], int] = {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _atomic_write(path: Path, text: str) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except OSError:
            pass
        raise


def _write_json(path: Path, value: Any) -> None:
    _atomic_write(path, json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}


def _root_key(call_root: Path) -> str:
    return str(Path(call_root).absolute())


def _used_attempt_numbers(call_root: Path) -> list[int]:
    attempts = Path(call_root) / "attempts"
    if not attempts.is_dir():
        return []
    return sorted(
        int(child.name)
        for child in attempts.iterdir()
        if child.is_dir() and child.name.isdigit()
    )


def _physical_attempt(call_root: Path, attempt: int) -> int:
    return _ACTIVE_ATTEMPT_MAP.get((_root_key(call_root), int(attempt)), int(attempt))


def attempt_dir(call_root: Path, attempt: int, *, create: bool = True) -> Path:
    physical = _physical_attempt(call_root, attempt)
    path = Path(call_root) / "attempts" / f"{physical:02d}"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def syntax_attempt_dir(call_root: Path, parent_attempt: int, attempt: int, *, create: bool = True) -> Path:
    path = attempt_dir(call_root, parent_attempt, create=create) / "syntax_repairs" / f"{int(attempt):02d}"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def begin_attempt(
    call_root: Path,
    attempt: int,
    *,
    messages: list[dict[str, Any]],
    prompt: str,
    metadata: dict[str, Any],
    parent_attempt: int | None = None,
) -> Path:
    logical_attempt = int(attempt)
    if parent_attempt is None:
        used = _used_attempt_numbers(call_root)
        requested_path = Path(call_root) / "attempts" / f"{logical_attempt:02d}"
        physical_attempt = max(used, default=0) + 1 if requested_path.exists() else logical_attempt
        _ACTIVE_ATTEMPT_MAP[(_root_key(call_root), logical_attempt)] = physical_attempt
        path = attempt_dir(call_root, logical_attempt)
    else:
        physical_attempt = logical_attempt
        path = syntax_attempt_dir(call_root, parent_attempt, logical_attempt)

    _write_json(path / "messages.json", messages)
    _atomic_write(path / "prompt.md", prompt)
    document = {
        "schema_version": SCHEMA_VERSION,
        **metadata,
        "attempt": int(physical_attempt),
        "status": "running",
        "started_at": metadata.get("started_at") or _now(),
        "accepted": False,
    }
    if parent_attempt is None:
        if physical_attempt != logical_attempt:
            document["logical_attempt"] = logical_attempt
            document["resumed_attempt"] = True
        if logical_attempt > 1:
            document["attempt_kind"] = "task_retry"
        elif physical_attempt != logical_attempt:
            document["attempt_kind"] = "semantic_redo"
        else:
            document["attempt_kind"] = "initial"
    if parent_attempt is not None:
        document["parent_attempt"] = _physical_attempt(call_root, parent_attempt)
        document["attempt_kind"] = "syntax_repair"
    _write_json(path / "call.json", document)
    if parent_attempt is None:
        call_id = str(metadata.get("call_id") or metadata.get("logical_operation") or Path(call_root).name)
        kind = document["attempt_kind"].replace("_", " ")
        print(f"[model] {call_id}: {kind} · physical attempt {physical_attempt}", file=sys.stderr, flush=True)
    return path


def write_raw_output(path: Path, text: str) -> None:
    _atomic_write(Path(path) / "output.txt", str(text))


def write_reasoning(path: Path, reasoning: str | None) -> None:
    target = Path(path) / "reasoning.md"
    if reasoning is None:
        try:
            target.unlink()
        except FileNotFoundError:
            pass
        return
    _atomic_write(target, str(reasoning))


def finish_attempt(path: Path, *, status: str, **fields: Any) -> dict[str, Any]:
    target = Path(path) / "call.json"
    document = _read_json(target)
    document.update({key: value for key, value in fields.items() if value is not None})
    document["schema_version"] = SCHEMA_VERSION
    document["status"] = status
    if status != "running":
        document["completed_at"] = fields.get("completed_at") or _now()
    document["accepted"] = status == "accepted"
    _write_json(target, document)
    return document


def write_validation(path: Path, *, accepted: bool, detail: str | None = None) -> None:
    lines = [f"RESULT={'accepted' if accepted else 'rejected'}"]
    if detail:
        lines.extend(("", str(detail).rstrip()))
    _atomic_write(Path(path) / "validation.txt", "\n".join(lines) + "\n")


def sync_root_compatibility_view(call_root: Path, source: Path) -> None:
    call_root, source = Path(call_root), Path(source)
    for name in ("messages.json", "prompt.md", "output.txt", "reasoning.md"):
        origin, target = source / name, call_root / name
        if origin.is_file():
            _atomic_write(target, origin.read_text(encoding="utf-8"))
        elif name == "reasoning.md":
            try:
                target.unlink()
            except FileNotFoundError:
                pass


def mirror_legacy_syntax_view(source: Path, legacy_root: Path) -> None:
    """Keep the established syntax handoff/debug path while nested history is authoritative."""
    source, legacy_root = Path(source), Path(legacy_root)
    legacy_root.mkdir(parents=True, exist_ok=True)
    for name in ("messages.json", "prompt.md", "output.txt", "reasoning.md"):
        origin = source / name
        if origin.is_file():
            _atomic_write(legacy_root / name, origin.read_text(encoding="utf-8"))


def _relative(path: Path, work: Path) -> str:
    return path.relative_to(work).as_posix()


def _attempt_row(path: Path, work: Path) -> dict[str, Any]:
    metadata = _read_json(path / "call.json")
    row = {
        "attempt": int(metadata.get("attempt") or path.name),
        "status": metadata.get("status") or "running",
        "path": _relative(path, work),
        "attempt_kind": metadata.get("attempt_kind") or ("semantic_redo" if metadata.get("resumed_attempt") else "initial"),
    }
    repairs = path / "syntax_repairs"
    row["syntax_repairs"] = [
        _attempt_row(child, work)
        for child in sorted(repairs.iterdir())
        if child.is_dir() and child.name.isdigit() and (child / "call.json").is_file()
    ] if repairs.is_dir() else []
    return row


def _call_rows(work: Path) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    rows: list[tuple[dict[str, Any], dict[str, Any]]] = []
    roots = Path(work) / "model_steps"
    if not roots.is_dir():
        return rows
    for root in sorted(roots.iterdir()):
        attempts = root / "attempts"
        if not root.is_dir() or not attempts.is_dir():
            continue
        paths = [
            child for child in sorted(attempts.iterdir())
            if child.is_dir() and child.name.isdigit() and (child / "call.json").is_file()
        ]
        if not paths:
            continue
        metadata = _read_json(paths[-1] / "call.json")
        if metadata.get("call_kind", "model") != "model":
            continue
        attempt_rows = [_attempt_row(path, work) for path in paths]
        latest_status = attempt_rows[-1]["status"]
        status = "complete" if latest_status == "accepted" else latest_status
        rows.append((metadata, {
            "call_id": metadata.get("call_id") or root.name,
            "role": metadata.get("role"),
            "status": status,
            "path": _relative(root, work),
            "attempts": attempt_rows,
        }))
    return rows



def invalidate_compatibility_view(work: Path, logical_operation: str) -> None:
    """Clear only mutable root-level views for one invalidated logical model step.

    Numeric attempt directories remain immutable audit history. The canonical
    structured workflow artifact is removed separately by the executor.
    """
    roots = Path(work) / "model_steps"
    if not roots.is_dir():
        return
    for root in roots.iterdir():
        attempts = root / "attempts"
        if not root.is_dir() or not attempts.is_dir():
            continue
        paths = [
            child for child in sorted(attempts.iterdir())
            if child.is_dir() and child.name.isdigit() and (child / "call.json").is_file()
        ]
        if not paths:
            continue
        metadata = _read_json(paths[-1] / "call.json")
        if str(metadata.get("logical_operation") or "") != str(logical_operation):
            continue
        for name in ("accepted-output.txt", "validated.txt", "output.txt", "reasoning.md", "messages.json", "prompt.md"):
            try:
                (root / name).unlink()
            except FileNotFoundError:
                pass


def _humanize(logical_id: str) -> str:
    return logical_id.replace("_", " ").replace(".", " · ").strip().title()


def build_model_operation_index(
    work: Path,
    *,
    workflow_steps: Iterable[str] = (),
    labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    work = Path(work)
    order = {step_id: index for index, step_id in enumerate(workflow_steps)}
    grouped: dict[str, dict[str, Any]] = {}
    for metadata, call in _call_rows(work):
        logical_id = str(metadata.get("logical_operation") or call["call_id"])
        operation = grouped.setdefault(logical_id, {
            "id": logical_id,
            "label": (labels or {}).get(logical_id) or _humanize(logical_id),
            "order": order.get(logical_id),
            "status": "complete",
            "calls": [],
        })
        operation["calls"].append(call)
        statuses = [row["status"] for row in operation["calls"]]
        operation["status"] = "running" if "running" in statuses else (
            "complete" if "complete" in statuses else statuses[-1]
        )
    unknown = len(order)
    operations = sorted(
        grouped.values(),
        key=lambda row: (row["order"] is None, row["order"] if row["order"] is not None else unknown, row["id"]),
    )
    document = {"schema_version": SCHEMA_VERSION, "operations": operations}
    target = work / "logs" / INDEX_NAME
    _write_json(target, document)
    return document
