"""Validate a model artifact against its declared stage asset.

Structure comes from the stage's JSON Schema; relational constraints come from
the named rules the asset declares. Both produce `ValidationIssue`, so feedback
is indistinguishable from the hand-written validators this replaces — which is
the acceptance criterion for Phase 5: a structural refactor must not change what
the model is told.
"""
from __future__ import annotations

import re

from scripts.core.validated_model_task import fail
from workflows.terraced_v6 import issues as iss
from workflows.terraced_v6 import rules as rule_registry
from workflows.terraced_v6 import schema_engine, stage_spec


def _path_key(issue):
    """Sort issues into document order, with numeric indices ordered naturally.

    Schema errors and relational-rule errors arrive from two different passes, so
    without this the model reads defects in engine order rather than in the order
    they appear in its own artifact.
    """
    parts = []
    for chunk in re.split(r"[.\[\]]+", issue.path or ""):
        if not chunk:
            continue
        parts.append((0, int(chunk), "") if chunk.isdigit() else (1, 0, chunk))
    return parts


def validate(stage: str, text: str, context: dict | None = None) -> str:
    spec = stage_spec.load(stage)
    label = spec.label
    doc, problems = iss.parse(text, fmt=spec.output_format, context=label)
    if problems:
        fail(label, problems)
    problems = schema_engine.issues_from_schema(doc, schema_engine.load(spec.schema_name), context=label)
    problems += rule_registry.apply(spec, doc, context or {})
    fail(label, sorted(problems, key=_path_key))
    return f"{label} valid"
