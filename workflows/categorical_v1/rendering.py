"""Categorical-v1 evidence rendering policy."""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

from scripts.core import card_tags
from scripts.core import rendering as core


def render_header(bundle):
    provenance = bundle.get("provenance", {})
    initial_cmc = bundle.get("initial_case_major_category") or bundle.get("case_major_category")
    refined_cmc = bundle.get("refined_case_major_category") or initial_cmc
    out = [
        "# Evidence block",
        "",
        textwrap.fill(
            "Collated evidence cards, not a report. Source, evidence tier and disease "
            "context are grouped above each card interpretation; report synthesis happens "
            "downstream.",
            width=core.WRAP_WIDTH,
        ),
        "",
        f"Genes submitted: {', '.join(bundle.get('genes', [])) or 'none'}",
        f"Step-1 case major category: {initial_cmc}",
    ]
    if bundle.get("render_profile") == "diagnosis_first_downstream":
        out.extend([
            f"Step-3 refined case major category: {refined_cmc}",
            f"Case major category changed: {'yes' if refined_cmc != initial_cmc else 'no'}",
        ])
    out.append(
        f"Corpus {provenance.get('corpus_version')} "
        f"sha256 {str(provenance.get('corpus_sha256'))[:16]}..., "
        f"retrieved {provenance.get('retrieved_at')}"
    )
    return out


def extra_tail(_bundle):
    return []


def render(bundle, token_budget=core.DEFAULT_TOKEN_BUDGET):
    return core.render(
        bundle,
        header_renderer=render_header,
        extra_tail_renderer=extra_tail,
        token_budget=token_budget,
    )


def render_to_files(
    bundle_path: Path,
    *,
    output: Path | None = None,
    card_tag_output: Path | None = None,
    token_budget: int = core.DEFAULT_TOKEN_BUDGET,
    retrieved_only: bool = False,
):
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    if bundle.get("step") != 4:
        raise ValueError("render expects a step 4 bundle from retrieve.py")
    if bundle.get("workflow_profile") != "categorical-v1":
        raise ValueError("categorical renderer requires a categorical-v1 bundle")
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
        card_tag_output.write_text(
            json.dumps(tag_map, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
    print(
        f"[render] {result['cards_rendered']}/{result['cards_available']} model-facing card(s) rendered "
        f"({result['cards_retrieved']} Step-4 retrieved), {len(result['references'])} reference(s), "
        f"~{result['estimated_tokens']} tokens (estimate: {result['token_estimate_method']}) "
        f"against a budget of {result['token_budget']}",
        file=sys.stderr,
    )
    return result
