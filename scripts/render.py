#!/usr/bin/env python3
"""Dispatch evidence rendering to the workflow bound to the bundle work directory."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.core.card_tags import build_card_tags as _build_card_tags  # noqa: E402
from scripts.core.rendering import DEFAULT_TOKEN_BUDGET, evidence_markdown  # noqa: E402
from scripts.workflow_registry import (  # noqa: E402
    import_workflow_entrypoint,
    normalise_selector,
    workflow_for_work_dir,
)


def build_card_tags(rendered_cards):
    """Build runtime tags from the rendered-card compatibility shape."""
    return _build_card_tags(card["card_id"] for card in rendered_cards)


def render(bundle, token_budget=DEFAULT_TOKEN_BUDGET):
    """Render an in-memory bundle through the default workflow policy.

    Kept as a compatibility API for callers that used ``scripts/render.py``
    before workflow-specific rendering was split into workflow modules.
    """
    rendering = import_workflow_entrypoint(normalise_selector(None), "rendering")
    return rendering.render(bundle, token_budget=token_budget)


def render_bundle(
    bundle: Path,
    *,
    output: Path | None = None,
    card_tag_output: Path | None = None,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    retrieved_only: bool = False,
):
    work_dir = bundle.resolve().parent
    workflow_id, _metadata = workflow_for_work_dir(work_dir)
    rendering = import_workflow_entrypoint(workflow_id, "rendering")
    implementation = getattr(rendering, "render_to_files", None)
    if implementation is None:
        raise ValueError(f"workflow {workflow_id!r} does not implement rendering.render_to_files")
    return implementation(
        bundle.resolve(),
        output=output.resolve() if output else None,
        card_tag_output=card_tag_output.resolve() if card_tag_output else None,
        token_budget=token_budget,
        retrieved_only=retrieved_only,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--token-budget", type=int, default=DEFAULT_TOKEN_BUDGET)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--retrieved-only", action="store_true")
    parser.add_argument("--card-tag-output", type=Path)
    args = parser.parse_args()
    try:
        render_bundle(
            args.bundle,
            output=args.output,
            card_tag_output=args.card_tag_output,
            token_budget=args.token_budget,
            retrieved_only=args.retrieved_only,
        )
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"render failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
