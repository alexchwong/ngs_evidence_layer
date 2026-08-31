#!/usr/bin/env python3
"""Resolve registered workflow identities and persistent work-directory state."""
from __future__ import annotations

import importlib
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_PATH = REPO_ROOT / "workflows" / "registry.json"
STATE_FILENAME = "workflow.json"
WORKFLOW_ID_PATTERN = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


def load_registry(path: Path = REGISTRY_PATH) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("schema_version") != 1 or not isinstance(data.get("workflows"), dict):
        raise ValueError(f"invalid workflow registry: {path}")

    # A source checkout can retain legacy/development workflow registrations, while
    # a stripped release may ship only the canonical workflow plus explicitly supported
    # compatibility implementations. Treat registered workflows whose implementation
    # directory is absent as disabled so release routing cannot select unshipped code.
    for row in data["workflows"].values():
        relative = row.get("path") if isinstance(row, dict) else None
        if isinstance(relative, str) and not (REPO_ROOT / relative).is_dir():
            row["enabled"] = False
    return data


def normalise_selector(selector: str | None, registry: dict | None = None) -> str:
    registry = registry or load_registry()
    if not selector:
        return registry["default_workflow"]
    selector = selector.removeprefix("--")
    selector = registry.get("aliases", {}).get(selector, selector)
    if selector not in registry["workflows"]:
        choices = sorted(set(registry["workflows"]) | set(registry.get("aliases", {})))
        raise ValueError(
            f"unknown workflow selector {selector!r}; choose one of: " + ", ".join(choices)
        )
    if not registry["workflows"][selector].get("enabled", True):
        raise ValueError(f"workflow {selector!r} is disabled")
    return selector


def workflow_dir(workflow_id: str, registry: dict | None = None) -> Path:
    registry = registry or load_registry()
    try:
        relative = registry["workflows"][workflow_id]["path"]
    except KeyError as exc:
        raise ValueError(f"workflow {workflow_id!r} is not registered") from exc
    path = (REPO_ROOT / relative).resolve()
    if not path.is_dir():
        raise ValueError(f"registered workflow directory is missing: {path}")
    return path


def load_workflow_metadata(workflow_id: str, registry: dict | None = None) -> dict:
    path = workflow_dir(workflow_id, registry) / "workflow.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("workflow_id") != workflow_id:
        raise ValueError(
            f"workflow metadata mismatch: registry selects {workflow_id!r} but {path} "
            f"declares {data.get('workflow_id')!r}"
        )
    if data.get("schema_version") != 1:
        raise ValueError(f"unsupported workflow metadata schema in {path}")
    return data


def state_path(work_dir: Path) -> Path:
    return Path(work_dir) / STATE_FILENAME


def read_workflow_state(work_dir: Path) -> dict:
    path = state_path(work_dir)
    if not path.is_file():
        raise ValueError(
            f"workflow state is missing: {path}. Run scripts/setup_workflow.py for this "
            "work directory before any downstream deterministic command."
        )
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"workflow state is invalid JSON: {path}: {exc}") from exc
    workflow_id = state.get("workflow_id")
    if state.get("schema_version") != 1 or not isinstance(workflow_id, str):
        raise ValueError(f"workflow state is malformed: {path}")
    load_workflow_metadata(workflow_id)
    return state


def write_workflow_state(
    work_dir: Path,
    workflow_id: str,
    mode: str,
    model_profile: str | None = None,
) -> Path:
    work_dir = Path(work_dir).resolve()
    existing_path = state_path(work_dir)
    existing_profile = None
    if existing_path.is_file():
        existing = read_workflow_state(work_dir)
        if existing["workflow_id"] != workflow_id:
            raise ValueError(
                f"work directory is already bound to workflow {existing['workflow_id']!r}; "
                f"refusing to reopen it as {workflow_id!r}. Use a new work directory."
            )
        existing_profile = existing.get("model_profile")
    payload = {
        "schema_version": 1,
        "workflow_id": workflow_id,
        "mode": mode,
    }
    # Additive and optional. Persisting it means a resumed work directory keeps
    # its binding without the caller repeating flags on every later command.
    profile = model_profile if model_profile is not None else existing_profile
    if profile:
        payload["model_profile"] = profile
    existing_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return existing_path


def import_workflow_module(workflow_id: str, module_name: str):
    """Import one module from a workflow package by module name."""
    metadata = load_workflow_metadata(workflow_id)
    package = metadata.get("python_package")
    if not isinstance(package, str) or not package:
        raise ValueError(f"workflow {workflow_id!r} has no python_package")
    return importlib.import_module(f"{package}.{module_name}")


def import_workflow_entrypoint(workflow_id: str, entrypoint: str):
    """Import a workflow-declared implementation without naming workflows here."""
    metadata = load_workflow_metadata(workflow_id)
    entrypoints = metadata.get("entrypoints") or {}
    module_name = entrypoints.get(entrypoint)
    if not isinstance(module_name, str) or not module_name:
        raise ValueError(
            f"workflow {workflow_id!r} has no declared {entrypoint!r} entrypoint"
        )
    return import_workflow_module(workflow_id, module_name)


def workflow_for_work_dir(work_dir: Path) -> tuple[str, dict]:
    state = read_workflow_state(work_dir)
    workflow_id = state["workflow_id"]
    return workflow_id, load_workflow_metadata(workflow_id)
