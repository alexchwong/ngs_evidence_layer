#!/usr/bin/env python3
"""Developer helper to clone and validate isolated workflow implementations."""
from __future__ import annotations

import argparse
import json
import py_compile
import re
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.workflow_registry import (
    REGISTRY_PATH,
    WORKFLOW_ID_PATTERN,
    load_registry,
    load_workflow_metadata,
    normalise_selector,
    workflow_dir,
)


def package_name_for(workflow_id: str) -> str:
    return workflow_id.replace("-", "_")


def _write_registry(registry: dict) -> None:
    REGISTRY_PATH.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def create_workflow(source_selector: str, new_id: str) -> Path:
    if not WORKFLOW_ID_PATTERN.fullmatch(new_id):
        raise ValueError("workflow ID must contain only lowercase letters, digits and single hyphens")
    registry = load_registry()
    source_id = normalise_selector(source_selector, registry)
    if new_id in registry["workflows"] or new_id in registry.get("aliases", {}):
        raise ValueError(f"workflow ID or alias already exists: {new_id}")

    source_dir = workflow_dir(source_id, registry)
    source_meta = load_workflow_metadata(source_id, registry)
    destination_rel = f"workflows/{package_name_for(new_id)}"
    destination = REPO_ROOT / destination_rel
    if destination.exists():
        raise ValueError(f"destination already exists: {destination}")
    shutil.copytree(source_dir, destination, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    source_rel = registry["workflows"][source_id]["path"]
    source_package = source_meta["python_package"]
    destination_package = f"workflows.{package_name_for(new_id)}"
    for path in destination.rglob("*"):
        if not path.is_file() or path.suffix not in {".py", ".md", ".json"}:
            continue
        text = path.read_text(encoding="utf-8")
        text = text.replace(source_rel, destination_rel)
        text = text.replace(source_package, destination_package)
        text = text.replace(source_id, new_id)
        path.write_text(text, encoding="utf-8")

    metadata_path = destination / "workflow.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["workflow_id"] = new_id
    metadata["python_package"] = destination_package
    metadata["skill"] = f"{destination_rel}/SKILL.md"
    metadata["cloned_from"] = source_id
    metadata["status"] = "development"
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    registry["workflows"][new_id] = {"path": destination_rel, "enabled": True}
    _write_registry(registry)
    return destination


def check_workflow(selector: str) -> list[str]:
    registry = load_registry()
    workflow_id = normalise_selector(selector, registry)
    directory = workflow_dir(workflow_id, registry)
    metadata = load_workflow_metadata(workflow_id, registry)
    required = [directory / "SKILL.md", directory / "workflow.json", directory / "case_pipeline.py", directory / "retrieval.py"]
    missing = [str(path.relative_to(REPO_ROOT)) for path in required if not path.is_file()]
    if missing:
        raise ValueError("workflow is missing required file(s): " + ", ".join(missing))
    package = metadata.get("python_package")
    expected_package = f"workflows.{directory.name}"
    if package != expected_package:
        raise ValueError(f"python_package must be {expected_package!r}, found {package!r}")
    skill = metadata.get("skill")
    expected_skill = str((directory / "SKILL.md").relative_to(REPO_ROOT))
    if skill != expected_skill:
        raise ValueError(f"skill path must be {expected_skill!r}, found {skill!r}")
    artifacts = metadata.get("artifacts")
    if not isinstance(artifacts, list) or "workflow.json" not in artifacts:
        raise ValueError("workflow artifact manifest must be a list containing workflow.json")
    for py in directory.rglob("*.py"):
        py_compile.compile(str(py), doraise=True)
    notes = [f"workflow {workflow_id} is structurally valid", f"path: {directory.relative_to(REPO_ROOT)}"]
    status = metadata.get("status")
    if status not in {"accepted", "legacy", "development"}:
        raise ValueError("workflow metadata status must be accepted, legacy, or development")
    notes.append(f"status: {status}")
    if metadata.get("cloned_from"):
        notes.append(f"cloned from: {metadata['cloned_from']}")
    return notes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    new = sub.add_parser("new", help="clone one registered workflow")
    new.add_argument("--from", dest="source", required=True)
    new.add_argument("--name", required=True)
    check = sub.add_parser("check", help="validate one registered workflow")
    check.add_argument("workflow")
    args = parser.parse_args()
    try:
        if args.command == "new":
            path = create_workflow(args.source, args.name)
            print(path)
            for line in check_workflow(args.name):
                print(line)
        else:
            for line in check_workflow(args.workflow):
                print(line)
    except (OSError, ValueError, json.JSONDecodeError, py_compile.PyCompileError) as exc:
        parser.exit(1, f"workflow developer helper failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
