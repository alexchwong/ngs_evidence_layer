"""Default-workflow experimental configuration.

The default workflow keeps one execution graph while allowing small prompt and
meaning-preserving enrichment modules to be selected independently. Selection
is intentionally default-workflow-only for now.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

ENV_DEFAULT_CONFIG = "NEL_DEFAULT_CONFIG"
BLANK_SECTION = "(this section intentionally left blank)"
_BOUND_CONFIG: Path | None = None


def package_root() -> Path:
    return Path(__file__).resolve().parent


def config_dir() -> Path:
    return package_root() / "configs" / "default"


def available_configs() -> tuple[str, ...]:
    return tuple(sorted(path.stem for path in config_dir().glob("*.yaml") if path.is_file()))


def resolve_config(selection: str | Path | None = None) -> Path:
    if selection is None and _BOUND_CONFIG is not None:
        return _BOUND_CONFIG
    raw = str(selection or os.environ.get(ENV_DEFAULT_CONFIG) or "default").strip()
    candidate = Path(raw)
    if candidate.is_absolute():
        # UI/root-launched runs may point at a frozen copy captured inside the run.
        path = candidate.resolve()
    elif candidate.parent != Path(".") or candidate.suffix:
        path = (package_root() / candidate).resolve()
        root = package_root().resolve()
        try:
            path.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"relative default config escapes {root}: {path}") from exc
    else:
        path = (config_dir() / f"{raw}.yaml").resolve()
    if not path.is_file():
        raise ValueError(
            f"unknown default config {raw!r}; available: {', '.join(available_configs()) or 'none'}"
        )
    return path


def bind_config(selection: str | Path | None) -> Path | None:
    """Bind one explicit config for this process, or clear the process-local binding."""
    global _BOUND_CONFIG
    if selection is None:
        _BOUND_CONFIG = None
        return None
    _BOUND_CONFIG = resolve_config(selection)
    return _BOUND_CONFIG


def load(selection: str | Path | None = None) -> dict[str, Any]:
    path = resolve_config(selection)
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid default config {path}: {exc}") from exc
    if not isinstance(doc, dict):
        raise ValueError(f"default config must be a YAML mapping: {path}")
    if int(doc.get("version") or 0) != 1:
        raise ValueError(f"unsupported default config version in {path}: {doc.get('version')!r}")
    return doc


def module_spec(name: str, selection: str | Path | None = None) -> dict[str, Any]:
    doc = load(selection)
    modules = doc.get("prompt_modules") or {}
    if not isinstance(modules, dict) or name not in modules:
        raise ValueError(f"prompt module {name!r} is not configured in {resolve_config(selection)}")
    spec = modules[name]
    if not isinstance(spec, dict):
        raise ValueError(f"prompt module {name!r} config must be a mapping")
    enabled = spec.get("enabled")
    version = str(spec.get("version") or "").strip()
    if not isinstance(enabled, bool):
        raise ValueError(f"prompt module {name!r}.enabled must be boolean")
    if not version:
        raise ValueError(f"prompt module {name!r}.version is required")
    return {"enabled": enabled, "version": version}


def enrichment_spec(name: str, selection: str | Path | None = None) -> dict[str, Any]:
    doc = load(selection)
    enrichments = doc.get("deterministic_enrichments") or {}
    if not isinstance(enrichments, dict) or name not in enrichments:
        raise ValueError(f"deterministic enrichment {name!r} is not configured")
    spec = enrichments[name]
    if not isinstance(spec, dict):
        raise ValueError(f"deterministic enrichment {name!r} config must be a mapping")
    enabled = spec.get("enabled")
    version = str(spec.get("version") or "").strip()
    if not isinstance(enabled, bool):
        raise ValueError(f"deterministic enrichment {name!r}.enabled must be boolean")
    if not version:
        raise ValueError(f"deterministic enrichment {name!r}.version is required")
    return {"enabled": enabled, "version": version}


def enrichment_enabled(name: str, selection: str | Path | None = None) -> bool:
    return bool(enrichment_spec(name, selection)["enabled"])
