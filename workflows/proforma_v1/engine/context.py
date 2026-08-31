"""Typed mutable runtime context shared by workflow runners."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class WorkflowContext:
    work: Path
    executor: str
    profile: Any = None
    data: dict[str, Any] = field(default_factory=dict)
    completed: set[str] = field(default_factory=set)
    completed_groups: set[str] = field(default_factory=set)

    def put(self, key: str, value: Any) -> Any:
        self.data[key] = value
        return value

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)
