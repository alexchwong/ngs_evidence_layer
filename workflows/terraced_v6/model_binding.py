"""Provider/model binding value object for terraced-v6 pipeline roles."""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Binding:
    pipeline: str
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
    def profile(self) -> str:
        """Compatibility alias used by existing model-client diagnostics."""
        return self.pipeline

    @property
    def is_self(self) -> bool:
        return self.kind == "self"

    def describe(self) -> str:
        if self.is_self:
            return f"{self.role}: pipeline={self.pipeline} provider=self"
        return (
            f"{self.role}: pipeline={self.pipeline} provider={self.kind} model={self.model} "
            f"base_url={self.base_url} temperature={self.temperature} max_tokens={self.max_tokens}"
        )
