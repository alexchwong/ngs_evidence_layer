"""Generic, fact-preserving syntax repair for structured model output."""
from .adapters import JsonSyntaxAdapter, SyntaxParseError, YamlSyntaxAdapter, adapter_for
from .core import (
    PreservationFingerprint,
    SYNTAX_REPAIR_SYSTEM_PROMPT,
    SyntaxRepairAttempt,
    SyntaxRepairExhausted,
    SyntaxRepairResult,
    content_fingerprint,
    preservation_error,
    repair_prompt,
    repair_structured_output,
    reserialization_prompt,
)

__all__ = [
    "JsonSyntaxAdapter",
    "PreservationFingerprint",
    "SYNTAX_REPAIR_SYSTEM_PROMPT",
    "SyntaxParseError",
    "SyntaxRepairAttempt",
    "SyntaxRepairExhausted",
    "SyntaxRepairResult",
    "YamlSyntaxAdapter",
    "adapter_for",
    "content_fingerprint",
    "preservation_error",
    "repair_prompt",
    "repair_structured_output",
    "reserialization_prompt",
]
