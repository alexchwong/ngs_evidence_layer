"""Declarative pipeline discovery and model/provider bindings for terraced-v3."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml

from workflows.terraced_v3.model_binding import Binding

HERE = Path(__file__).resolve().parent
ROOT = HERE / "pipelines"
ROLES = (
    "structure",
    "diagnosis",
    "ptbg",
    "evidence_alignment",
    "summarization",
    "summarization_review",
    "syntax_repair",
)
PHASES = ("diagnosis", "ptbg", "summarization")


@dataclass(frozen=True)
class PipelinePlan:
    pipeline_id: str
    description: str
    path: Path
    doc: dict[str, Any]

    @property
    def schedulers(self) -> dict[str, str]:
        return dict(self.doc["schedulers"])


def _paths() -> dict[str, Path]:
    rows = []
    if ROOT.is_dir():
        for path in ROOT.glob("*.yaml"):
            plan = load_yaml(path)
            rows.append((int((plan.doc.get("pipeline") or {}).get("order", 999)), plan.pipeline_id, path))
    out: dict[str, Path] = {}
    for _, pid, path in sorted(rows, key=lambda row: (row[0], row[1])):
        if pid in out:
            raise ValueError(f"duplicate pipeline id {pid!r}")
        out[pid] = path
    return out


def load_yaml(path: Path) -> PipelinePlan:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot read pipeline YAML {path}: {exc}") from exc
    if not isinstance(doc, dict):
        raise ValueError(f"pipeline YAML must be a mapping: {path}")
    meta = doc.get("pipeline")
    if not isinstance(meta, dict):
        raise ValueError("pipeline YAML requires pipeline mapping")
    pid = meta.get("id")
    if not isinstance(pid, str) or not pid:
        raise ValueError("pipeline.id must be non-empty")
    if meta.get("version") != 1:
        raise ValueError(f"unsupported pipeline version {meta.get('version')!r}")
    provider = doc.get("provider")
    if not isinstance(provider, dict):
        raise ValueError("pipeline.provider must be a mapping")
    kind = provider.get("type")
    if kind not in {"self", "openai-compatible"}:
        raise ValueError(f"pipeline {pid!r} uses unsupported provider type {kind!r}")
    schedulers = doc.get("schedulers")
    if not isinstance(schedulers, dict) or set(schedulers) != set(PHASES):
        raise ValueError(f"pipeline.schedulers must map exactly {list(PHASES)}")
    if any(not isinstance(schedulers[p], str) or not schedulers[p] for p in PHASES):
        raise ValueError("every pipeline scheduler selector must be a non-empty string")
    models = doc.get("models")
    if not isinstance(models, dict) or set(models) != set(ROLES):
        raise ValueError(f"pipeline.models must map exactly {list(ROLES)}")
    for role in ROLES:
        row = models[role]
        if not isinstance(row, dict):
            raise ValueError(f"pipeline.models.{role} must be a mapping")
        model = row.get("model")
        if not isinstance(model, str) or not model:
            raise ValueError(f"pipeline.models.{role}.model must be non-empty")
        max_tokens = row.get("max_tokens")
        if not isinstance(max_tokens, int) or max_tokens <= 0:
            raise ValueError(f"pipeline.models.{role}.max_tokens must be a positive integer")
        temp = row.get("temperature", 0.0)
        if not isinstance(temp, (int, float)):
            raise ValueError(f"pipeline.models.{role}.temperature must be numeric")
    return PipelinePlan(pid, str(meta.get("description") or ""), path, doc)


def names() -> tuple[str, ...]:
    return tuple(_paths())


def load(name: str) -> PipelinePlan:
    paths = _paths()
    if name not in paths:
        raise ValueError(f"unknown terraced-v3 pipeline {name!r}; choose one of: {', '.join(paths)}")
    return load_yaml(paths[name])


def descriptions() -> dict[str, str]:
    return {name: load(name).description for name in names()}


def binding(plan: PipelinePlan, role: str) -> Binding:
    if role not in ROLES:
        raise ValueError(f"unknown pipeline model role {role!r}; choose one of: {', '.join(ROLES)}")
    provider = plan.doc["provider"]
    row = plan.doc["models"][role]
    kind = provider["type"]
    if kind == "self":
        return Binding(
            pipeline=plan.pipeline_id,
            role=role,
            kind="self",
            model="self",
            temperature=float(row.get("temperature", 0.0)),
            max_tokens=int(row["max_tokens"]),
        )
    base_url = str(provider.get("base_url") or "")
    env = str(provider.get("base_url_env") or "")
    if env and os.environ.get(env, "").strip():
        base_url = os.environ[env].strip()
    if not base_url:
        raise ValueError(f"pipeline {plan.pipeline_id!r} has no provider base_url")
    api_key_env = str(provider.get("api_key_env") or "")
    return Binding(
        pipeline=plan.pipeline_id,
        role=role,
        kind="openai-compatible",
        model=str(row["model"]),
        temperature=float(row.get("temperature", 0.0)),
        max_tokens=int(row["max_tokens"]),
        base_url=base_url.rstrip("/"),
        base_url_env=env,
        api_key_env=api_key_env,
        api_key=os.environ.get(api_key_env, "") if api_key_env else "",
        timeout_s=float(provider.get("timeout_s", 900.0)),
    )


def describe(plan: PipelinePlan) -> list[str]:
    lines = [f"provider: {plan.doc['provider']['type']}"]
    for phase in PHASES:
        lines.append(f"{phase} scheduler: {plan.schedulers[phase]}")
    for role in ROLES:
        row = plan.doc["models"][role]
        lines.append(f"model {role}: {row['model']} max_tokens={row['max_tokens']} temperature={row.get('temperature', 0.0)}")
    return lines
