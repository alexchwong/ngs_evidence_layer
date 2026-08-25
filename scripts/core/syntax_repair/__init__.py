"""Generic, fact-preserving syntax repair for structured model output."""
from .adapters import JsonSyntaxAdapter, SyntaxParseError, YamlSyntaxAdapter, adapter_for
from .core import (
    PreservationFingerprint,
    SYNTAX_REPAIR_SYSTEM_PROMPT,
    SyntaxRepairAttempt,
    SyntaxRepairExhausted,
    SchemaSerializationRepairExhausted,
    SyntaxRepairResult,
    content_fingerprint,
    preservation_error,
    repair_prompt,
    schema_serialization_prompt,
    repair_schema_serialization,
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
    "SchemaSerializationRepairExhausted",
    "SyntaxRepairResult",
    "YamlSyntaxAdapter",
    "adapter_for",
    "content_fingerprint",
    "preservation_error",
    "repair_prompt",
    "schema_serialization_prompt",
    "repair_schema_serialization",
    "repair_structured_output",
    "reserialization_prompt",
]
