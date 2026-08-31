"""Standalone, model-free access to every proforma-v1 validated stage.

Each stage is registered with a validator that takes a candidate artifact plus a
plain-dict context, and (where applicable) a skeleton renderer. That makes two
things possible without a run directory, a corpus or a model:

- `python -m unittest discover -s workflows/proforma_v1/tests` walks `tests/fixtures/<stage>/` and
  asserts each stage's feedback text character-for-character, so the wording the
  model actually receives is a reviewed artifact rather than an accident;
- `step.py check-stage --stage prognosis --file candidate.yaml` prints exactly
  what the model would be told, in about a second.

The context dict is the small amount of runtime state a validator needs — the
variant registry, the supplied evidence item IDs, the block IDs. Fixtures store
it as `context.yaml`.
"""
from __future__ import annotations

from pathlib import Path

from workflows.proforma_v1 import domain_contract, stage_spec, stage_validation

FIXTURES = Path(__file__).resolve().parent / "tests" / "fixtures"


def _variants(context):
    return set(context.get("variants") or [])


def _items(context):
    """Evidence items as the batch validators expect them."""
    return [
        {"evidence_id": row["evidence_id"], "candidate_card_tags": list(row.get("candidate_card_tags") or [])}
        for row in context.get("items") or []
    ]


def _blocks(context):
    return [{"block_id": b} for b in context.get("blocks") or []]


def _domain_skeleton(domain):
    def render(context):
        return domain_contract.skeleton(
            domain_contract.contract(domain),
            sorted(_variants(context)),
            registry=context.get("registry") or {},
            applicable_disease=context.get("authoritative_disease"),
        )

    return render


def _spec_check(stage):
    def check(text, context):
        return stage_validation.validate(stage, text, _context_for(stage, context))

    return check


def _context_for(stage, context):
    """Normalise a fixture/runtime context into what the named rules expect."""
    ctx = dict(context or {})
    ctx.setdefault("variants", sorted(_variants(ctx)))
    return ctx


STAGES = {
    stage: {
        "check": _spec_check(stage),
        "format": stage_spec.load(stage).output_format,
        **({"skeleton": _domain_skeleton(stage)} if stage in stage_spec.domains() else {}),
    }
    for stage in stage_spec.names()
}


def names():
    return tuple(sorted(STAGES))


def check(stage: str, text: str, context: dict) -> str:
    """Run one stage's validator. Raises ValidationFailure with all issues."""
    if stage not in STAGES:
        raise ValueError(f"unknown stage {stage!r}; choose one of: {', '.join(names())}")
    return STAGES[stage]["check"](text, context or {})


def skeleton(stage: str, context: dict) -> str | None:
    """Render the model-facing output contract, where the stage has one."""
    render = STAGES.get(stage, {}).get("skeleton")
    return render(context or {}) if render else None


def fixture_dir(stage: str) -> Path:
    return FIXTURES / stage


def fixture_context(stage: str) -> dict:
    import yaml

    path = fixture_dir(stage) / "context.yaml"
    if not path.is_file():
        return {}
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
