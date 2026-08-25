"""Terraced-v1 evidence rendering."""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

from scripts.core import card_tags
from scripts.core import rendering as core


def render_header(bundle):
    provenance = bundle.get("provenance", {})
    out = [
        "# Evidence",
        "",
        textwrap.fill(
            "Collated evidence cards for one terraced clinical category. Card tags are runtime identifiers; "
            "clinical answering should state facts and reasons without selecting citations.",
            width=core.WRAP_WIDTH,
        ),
        "",
        f"Category: {bundle.get('terraced_domain', 'diagnosis')}",
        f"Genes submitted: {', '.join(bundle.get('genes', [])) or 'none'}",
    ]
    cmcs = bundle.get("provisional_cmcs") or []
    if cmcs:
        out.append(f"Provisional CMCs: {' | '.join(cmcs)}")
    diagnoses = bundle.get("accepted_schema_diseases") or []
    if diagnoses:
        out.append(f"Accepted schema diseases: {' | '.join(diagnoses)}")
    out.append(
        f"Corpus {provenance.get('corpus_version')} sha256 "
        f"{str(provenance.get('corpus_sha256'))[:16]}..., retrieved {provenance.get('retrieved_at')}"
    )
    return out


def render(bundle, token_budget=core.DEFAULT_TOKEN_BUDGET):
    return core.render(bundle, header_renderer=render_header, extra_tail_renderer=lambda _bundle: [], token_budget=token_budget)


def render_to_files(
    bundle_path: Path,
    *,
    output: Path | None = None,
    card_tag_output: Path | None = None,
    token_budget: int = core.DEFAULT_TOKEN_BUDGET,
    retrieved_only: bool = False,
):
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    if bundle.get("workflow_profile") != "terraced-v1":
        raise ValueError("terraced renderer requires a terraced-v1 bundle")
    if retrieved_only:
        bundle = dict(bundle)
        bundle["diagnostic_context"] = []
    result = render(bundle, token_budget)
    global_tag_map = bundle.get("runtime_card_tags") or card_tags.build_card_tags(
        card["card_id"] for card in result["rendered_cards"]
    )
    tag_map = card_tags.subset_tag_map(
        global_tag_map, [card["card_id"] for card in result["rendered_cards"]]
    )
    payload = core.evidence_markdown(result, tag_map)
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    if card_tag_output:
        card_tag_output.parent.mkdir(parents=True, exist_ok=True)
        card_tag_output.write_text(json.dumps(tag_map, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(
        f"[terraced render] {result['cards_rendered']}/{result['cards_available']} cards, ~{result['estimated_tokens']} tokens",
        file=sys.stderr,
    )
    return result
