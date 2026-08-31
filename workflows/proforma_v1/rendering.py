"""Proforma-v1 evidence rendering."""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

from scripts.core import card_tags
from scripts.core import rendering as core




def _prompt_source_hint(card: dict) -> str:
    return core.inline_text(
        card.get("source_hint") or card.get("paper_nickname") or card.get("citation_display") or card.get("publication_key"),
        "unspecified source",
    )


def _prompt_diseases(card: dict) -> tuple[str, ...]:
    values = [core.inline_text(x) for x in (card.get("diseases") or []) if str(x).strip()]
    return tuple(sorted(dict.fromkeys(values), key=str.casefold))


def render_prompt_cards(cards: list[dict], tag_by_id: dict[str, str], *, mode: str = "compact") -> str:
    """Render evidence cards for model prompts using runtime 12-hex tags only.

    Compact mode groups repeated metadata once as source -> category -> diseases and
    emits one evidence card per line. Verbose mode preserves the older per-card
    metadata layout for debugging, but still hides canonical stable card IDs from
    the model.
    """
    if mode not in {"compact", "verbose"}:
        raise ValueError("card rendering mode must be 'compact' or 'verbose'")
    if not cards:
        return "No candidate cards."

    def tag(card: dict) -> str:
        card_id = card.get("card_id")
        value = tag_by_id.get(card_id)
        if not value:
            raise ValueError(f"card {card_id!r} has no runtime tag")
        return value

    ordered = sorted(
        cards,
        key=lambda card: (
            _prompt_source_hint(card).casefold(),
            core.inline_text(card.get("category")).casefold(),
            tuple(x.casefold() for x in _prompt_diseases(card)),
            str(card.get("card_id") or ""),
        ),
    )

    if mode == "verbose":
        blocks = []
        for card in ordered:
            lines = [
                f"### [card:{tag(card)}]",
                f"category: {core.inline_text(card.get('category'))}",
                f"genes: {', '.join(card.get('genes') or []) or 'none'}",
                f"diseases: {', '.join(card.get('diseases') or []) or 'none'}",
                f"evidence_tier: {core.inline_text(card.get('evidence_tier'), 'unspecified')}",
                f"interpretation: {core.inline_text(card.get('interpretation'), '')}",
                f"source_hint: {_prompt_source_hint(card)}",
            ]
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    out: list[str] = []
    last_source = last_category = None
    last_diseases: tuple[str, ...] | None = None
    for card in ordered:
        source = _prompt_source_hint(card)
        category = core.inline_text(card.get("category"))
        diseases = _prompt_diseases(card)
        if source != last_source:
            if out:
                out.append("")
            out.append(f"## {source}")
            last_source = source
            last_category = None
            last_diseases = None
        if category != last_category:
            out.extend(["", f"### {category}"])
            last_category = category
            last_diseases = None
        if diseases != last_diseases:
            out.extend(["", f"#### {' | '.join(diseases) if diseases else 'none'}"])
            last_diseases = diseases
        interpretation = core.inline_text(card.get("interpretation"), "")
        tier = core.inline_text(card.get("evidence_tier"), "unspecified")
        out.append(f"[card:{tag(card)}] {interpretation} (evidence_tier: {tier})")
    return "\n".join(out).strip()


def render_diagnostic_prompt_cards(
    cards: list[dict],
    tag_by_id: dict[str, str],
    *,
    authority: str,
    mode: str = "compact",
) -> str:
    """Render one framework's already-filtered diagnostic card pool.

    Publication inclusion/exclusion belongs to pool construction, not formatting.
    Keeping this boundary diagnosis-specific makes it difficult for WHO5 or ICC
    prompts to accidentally render an unfiltered retrieval result while preserving
    the shared compact/verbose card layout.
    """
    if authority not in {"who5", "icc"}:
        raise ValueError(f"unsupported diagnosis authority: {authority!r}")
    non_diagnostic = [card.get("card_id") for card in cards if card.get("category") != "diagnosis"]
    if non_diagnostic:
        raise ValueError(
            f"{authority} diagnostic card pool contains non-diagnosis cards: "
            + ", ".join(str(card_id) for card_id in non_diagnostic)
        )
    if not cards:
        return f"No candidate {authority.upper()} diagnosis cards."
    return render_prompt_cards(cards, tag_by_id, mode=mode)


def render_header(bundle):
    provenance = bundle.get("provenance", {})
    out = [
        "# Evidence",
        "",
        textwrap.fill(
            "Collated evidence cards for one terraced clinical category. Card tags are runtime identifiers; "
            "clinical answering should state statements and reasons without selecting citations.",
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
    if bundle.get("workflow_profile") != "proforma-v1":
        raise ValueError("terraced renderer requires a proforma-v1 bundle")
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
