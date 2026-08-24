"""Standalone, model-free access to every terraced-v6 validated stage.

Each stage is registered with a validator that takes a candidate artifact plus a
plain-dict context, and (where applicable) a skeleton renderer. That makes two
things possible without a run directory, a corpus or a model:

- `pytest workflows/terraced_v6/tests/` walks `tests/fixtures/<stage>/` and
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

from workflows.terraced_v6 import domain_contract, schema_validation

FIXTURES = Path(__file__).resolve().parent / "tests" / "fixtures"


def _variants(context):
    return set(context.get("variants") or [])


def _items(context):
    """Evidence items as the batch validators expect them."""
    return [
        {"evidence_id": row["evidence_id"], "candidate_card_ids": list(row.get("candidate_card_ids") or [])}
        for row in context.get("items") or []
    ]


def _blocks(context):
    return [{"block_id": b} for b in context.get("blocks") or []]


def _domain_check(domain):
    def check(text, context):
        return schema_validation.validate_domain(text, domain, _variants(context))

    return check


def _domain_skeleton(domain):
    def render(context):
        return domain_contract.skeleton(domain_contract.contract(domain), sorted(_variants(context)))

    return render


STAGES = {
    "structure_case": {
        "check": lambda text, ctx: __import__(
            "workflows.terraced_v6.runtime", fromlist=["runtime"]
        ).validate_case_text(text, require_gene_prefixed_description=bool(ctx.get("require_gene_prefix"))),
        "format": "json",
    },
    "diagnosis_who5": {
        "check": lambda text, ctx: schema_validation.validate_who5_diagnosis(
            text,
            allowed_diseases=ctx.get("allowed_diseases") or [],
            valid_variants=_variants(ctx),
        ),
        "format": "yaml",
    },
    "diagnosis_icc": {
        "check": lambda text, ctx: schema_validation.validate_icc_diagnosis(text, valid_variants=_variants(ctx)),
        "format": "yaml",
    },
    "diagnosis_other": {
        "check": lambda text, ctx: schema_validation.validate_second_diagnosis(text, valid_variants=_variants(ctx)),
        "format": "yaml",
    },
    "evidence_match": {
        "check": lambda text, ctx: schema_validation.validate_evidence_match_batch(text, _items(ctx)),
        "format": "yaml",
    },
    "evidence_audit": {
        "check": lambda text, ctx: schema_validation.validate_evidence_audit_batch(text, _items(ctx)),
        "format": "yaml",
    },
    "report_write": {
        "check": lambda text, ctx: schema_validation.validate_report_write(text, _blocks(ctx)),
        "format": "yaml",
    },
    "report_preservation": {
        "check": lambda text, ctx: schema_validation.validate_preservation(text, _blocks(ctx)),
        "format": "yaml",
    },
}

for _domain in ("prognosis", "treatment", "biomarker", "germline"):
    STAGES[_domain] = {
        "check": _domain_check(_domain),
        "skeleton": _domain_skeleton(_domain),
        "format": "yaml",
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
