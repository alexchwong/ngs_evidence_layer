"""Canonical artifact reference helpers used by the declarative compiler."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArtifactRef:
    producer: str
    name: str
