#!/usr/bin/env python3
"""Resolve categorical-v1 model-role bindings from the workflow-local model registry.

Pure resolution logic. No network access, no workflow-step knowledge. Standard
library only, so that a registry check remains possible before the repository
virtual environment exists.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

WORKFLOW_DIR = Path(__file__).resolve().parent
REGISTRY_PATH = WORKFLOW_DIR / "models.json"
PROFILE_ENV = "NEL_MODEL_PROFILE"
SELF_PROVIDER = "self"
DELEGATING_PROVIDERS = ("openai-compatible",)


@dataclass(frozen=True)
class Binding:
    """One resolved role binding. Frozen so a step cannot mutate its own binding."""

    profile: str
    role: str
    kind: str
    model: str
    temperature: float = 0.0
    max_tokens: int = 8192
    base_url: str = ""
    base_url_env: str = ""
    api_key_env: str = ""
    api_key: str = ""
    timeout_s: float = 900.0

    @property
    def is_self(self) -> bool:
        return self.kind == SELF_PROVIDER

    def describe(self) -> str:
        if self.is_self:
            return f"{self.role}: profile={self.profile} provider=self (handoff to the session model)"
        return (
            f"{self.role}: profile={self.profile} provider={self.kind} model={self.model} "
            f"base_url={self.base_url} temperature={self.temperature} max_tokens={self.max_tokens}"
        )


def load_registry(path: Path = REGISTRY_PATH) -> dict:
    """Parse and structurally validate the model registry."""
    path = Path(path)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read model registry {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"model registry is invalid JSON: {path}: {exc}") from exc

    if data.get("schema_version") != 1:
        raise ValueError(f"unsupported model registry schema_version in {path}")
    profiles = data.get("profiles")
    if not isinstance(profiles, dict) or not profiles:
        raise ValueError(f"model registry has no profiles: {path}")
    default_profile = data.get("default_profile")
    if default_profile not in profiles:
        raise ValueError(
            f"model registry default_profile {default_profile!r} is not a registered profile in {path}"
        )
    roles = data.get("roles")
    if not isinstance(roles, list) or not roles:
        raise ValueError(f"model registry has no roles: {path}")
    for profile_id, profile in profiles.items():
        provider = (profile or {}).get("provider") or {}
        kind = provider.get("type")
        if kind != SELF_PROVIDER and kind not in DELEGATING_PROVIDERS:
            raise ValueError(
                f"profile {profile_id!r} declares unsupported provider type {kind!r}"
            )
        bindings = (profile or {}).get("roles") or {}
        missing = [role for role in roles if role not in bindings]
        if missing:
            raise ValueError(
                f"profile {profile_id!r} is missing bindings for role(s): " + ", ".join(missing)
            )
    return data


def _work_dir_profile(work_dir: Path | None) -> str | None:
    if work_dir is None:
        return None
    state_path = Path(work_dir) / "workflow.json"
    if not state_path.is_file():
        return None
    try:
        state = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    value = state.get("model_profile")
    return value if isinstance(value, str) and value else None


def resolve_profile(
    selector: str | None = None,
    work_dir: Path | None = None,
    registry: dict | None = None,
) -> str:
    """Resolve a profile ID.

    Order: explicit selector, then the work directory's recorded profile, then
    NEL_MODEL_PROFILE, then the registry default.
    """
    registry = registry or load_registry()
    candidate = None
    if selector:
        candidate = selector.removeprefix("--")
    if candidate is None:
        candidate = _work_dir_profile(work_dir)
    if candidate is None:
        env_value = os.environ.get(PROFILE_ENV, "").strip()
        candidate = env_value or None
    if candidate is None:
        candidate = registry["default_profile"]
    if candidate not in registry["profiles"]:
        registered = ", ".join(sorted(registry["profiles"]))
        raise ValueError(
            f"unknown model profile {candidate!r}; registered profiles: {registered}"
        )
    return candidate


def resolve(
    role: str,
    profile: str | None = None,
    work_dir: Path | None = None,
    registry: dict | None = None,
) -> Binding:
    """Resolve one role to a concrete binding."""
    registry = registry or load_registry()
    profile_id = resolve_profile(profile, work_dir, registry)
    profile_data = registry["profiles"][profile_id]
    if role not in (registry.get("roles") or []):
        registered = ", ".join(registry.get("roles") or [])
        raise ValueError(f"unknown model role {role!r}; registered roles: {registered}")
    binding = (profile_data.get("roles") or {}).get(role)
    if not isinstance(binding, dict):
        raise ValueError(f"profile {profile_id!r} has no binding for role {role!r}")

    provider = profile_data.get("provider") or {}
    kind = provider.get("type")
    model = binding.get("model") or ""
    temperature = float(binding.get("temperature", 0.0))
    max_tokens = int(binding.get("max_tokens", 8192))

    if kind == SELF_PROVIDER:
        return Binding(
            profile=profile_id,
            role=role,
            kind=SELF_PROVIDER,
            model="self",
            temperature=temperature,
            max_tokens=max_tokens,
        )

    if not model:
        raise ValueError(
            f"profile {profile_id!r} role {role!r} has no model ID. Set it in {REGISTRY_PATH}."
        )
    base_url_env = provider.get("base_url_env") or ""
    base_url = provider.get("base_url") or ""
    if base_url_env:
        override = os.environ.get(base_url_env, "").strip()
        if override:
            base_url = override
    if not base_url:
        raise ValueError(
            f"profile {profile_id!r} has no base_url and no non-empty {base_url_env or 'override'}"
        )
    api_key_env = provider.get("api_key_env") or ""
    api_key = os.environ.get(api_key_env, "") if api_key_env else ""

    return Binding(
        profile=profile_id,
        role=role,
        kind=kind,
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
        base_url=base_url.rstrip("/"),
        base_url_env=base_url_env,
        api_key_env=api_key_env,
        api_key=api_key,
        timeout_s=float(provider.get("timeout_s", 900)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", help="profile ID to resolve; default is the normal resolution order")
    parser.add_argument("--work-dir", type=Path, help="work directory whose recorded profile should be consulted")
    args = parser.parse_args()
    try:
        registry = load_registry()
        profile_id = resolve_profile(args.profile, args.work_dir, registry)
        print(f"registry: {REGISTRY_PATH}")
        print(f"profile:  {profile_id}")
        description = (registry["profiles"][profile_id] or {}).get("description")
        if description:
            print(f"summary:  {description}")
        for role in registry["roles"]:
            print("  " + resolve(role, profile_id, args.work_dir, registry).describe())
    except ValueError as exc:
        print(f"model registry check failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
