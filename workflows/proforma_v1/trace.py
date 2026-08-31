"""Machine-readable Phase 1 workflow/replay trace utilities."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

TRACE_SCHEMA_VERSION = 1


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@dataclass
class TraceRecorder:
    workflow: str
    operations: list[dict[str, Any]] = field(default_factory=list)

    def record(self, operation_id: str, operation_type: str, status: str, **fields: Any) -> None:
        row = {"id": operation_id, "type": operation_type, "status": status}
        for key, value in fields.items():
            if value is not None:
                row[key] = value
        self.operations.append(row)

    def document(self) -> dict[str, Any]:
        return {
            "schema_version": TRACE_SCHEMA_VERSION,
            "workflow": self.workflow,
            "operations": list(self.operations),
        }

    def write(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.document(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return path
