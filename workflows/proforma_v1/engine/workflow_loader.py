"""Load the declarative workflow document."""
from __future__ import annotations

from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parents[1]
DEFAULT_WORKFLOW = HERE / "workflow.yaml"


class WorkflowLoadError(ValueError):
    pass


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise WorkflowLoadError(f"duplicate YAML key {key!r} at line {key_node.start_mark.line + 1}")
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_mapping)


def load(path: Path | str | None = None) -> dict:
    path = Path(path or DEFAULT_WORKFLOW)
    try:
        doc = yaml.load(path.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    except WorkflowLoadError:
        raise
    except (OSError, yaml.YAMLError) as exc:
        raise WorkflowLoadError(f"cannot load workflow {path}: {exc}") from exc
    if not isinstance(doc, dict):
        raise WorkflowLoadError(f"workflow {path} must be a mapping")
    return doc
