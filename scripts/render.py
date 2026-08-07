#!/usr/bin/env python3
"""Render a step 4 retrieval bundle as a structured evidence-card block.

Quotes are never rendered or returned by retrieval; they remain private inside
accepted ingestion packages.
The rendered Markdown preserves one visible record per retrieved evidence card.
Each record includes its stable card ID, human-readable label, category, genes,
disease context, evidence tier, interpretation, source locator, and any
escalation target. Citations remain publication-style at the end of the block:
card IDs map to primary and secondary reference numbers in ``## Refs``, followed
by the numbered bibliography in ``## References``.
Citation numbering is scripted rather than modelled. Numbers fall out of the
deterministic card order, so the same corpus and case produce the same block,
and every number points at a reference contributed by a rendered card.

Order: category, then gene, then evidence tier strongest first, then publication
year descending, then card ID.

Usage:
  render.py --bundle bundle.json > block.md
  render.py --bundle bundle.json --token-budget 120000 --format json
"""
import argparse
import json
import re
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vocab  # noqa: E402

DEFAULT_TOKEN_BUDGET = 120_000
CHARS_PER_TOKEN = 4  # estimate; stated as an estimate wherever it is reported
WRAP_WIDTH = 78
# Truncation order. Guideline criteria and multivariable-adjusted findings are
# never dropped: if the block still will not fit after these two tiers are gone,
# the honest output is an over-budget block with a warning, not a quietly
# weakened one.
DROPPABLE_TIERS = ["restated secondary", "univariable or descriptive"]
CATEGORY_HEADINGS = {
    "diagnosis": "Diagnosis and classification",
    "prognosis": "Prognostic significance",
    "treatment": "Clinically actionable implications",
    "biomarker": "MRD and biomarker implications",
    "germline": "Possible germline predisposition",
}


def sort_key(card):
    return (
        vocab.CATEGORY_RANK.get(card["category"], len(vocab.CATEGORY_RANK)),
        min(card.get("genes") or ["ZZZZ"]),
        vocab.TIER_RANK.get(card["evidence_tier"], len(vocab.TIER_RANK)),
        -(card.get("publication_year") or 0),
        card["card_id"],
    )


def card_lines(cards):
    """Return one render record per card, preserving deterministic card order.
    Evidence cards are the atomic downstream evidence objects. Byte-identical
    interpretations are deliberately not collapsed: collapsing would hide
    card-level metadata and break the visible interpretation -> card ->
    reference chain required for downstream synthesis.
    """
    return [
        {
            "representative": card,
            "card_ids": [card["card_id"]],
            "members": [card],
        }
        for card in cards
    ]


def citation_entries(card):
    """The reference-list entries this card contributes, primary first."""
    entries = [{
        "key": card.get("publication_key") or card.get("citation_display"),
        "display": card.get("citation_display") or "[citation missing]",
        "citation_incomplete": card.get("citation_incomplete") or [],
        "kind": "primary",
    }]
    secondary = card.get("secondary_citation")
    if secondary:
        entries.append({
            "key": "secondary::" + (secondary.get("display") or ""),
            "display": secondary.get("display")
            or "[reference incomplete in source publication]",
            "citation_incomplete": secondary.get("citation_incomplete") or [],
            "kind": "secondary",
        })
    return entries


def assign_references(lines):
    """Assign numbers in order of first appearance and record per-card roles.
    Returns the ordered reference list and a map from card_id to its primary and
    secondary reference numbers.
    """
    numbers = {}
    references = []
    card_map = {}
    for line in lines:
        for member in line["members"]:
            card_id = member["card_id"]
            if card_id not in card_map:
                card_map[card_id] = {"primary_refs": [], "secondary_refs": []}
            for entry in citation_entries(member):
                key = entry["key"]
                if key not in numbers:
                    numbers[key] = len(references) + 1
                    references.append(entry)
                number = numbers[key]
                bucket = (
                    "primary_refs" if entry["kind"] == "primary"
                    else "secondary_refs"
                )
                if number not in card_map[card_id][bucket]:
                    card_map[card_id][bucket].append(number)
    for mapping in card_map.values():
        mapping["primary_refs"].sort()
        mapping["secondary_refs"].sort()
    return references, card_map


def estimate_tokens(text):
    return max(1, (len(text) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN)


def inline_text(value, fallback="not specified"):
    """Normalise a scalar to one deterministic Markdown-safe display line."""
    if value is None:
        return fallback
    text = " ".join(str(value).split())
    return text or fallback


def list_text(values, fallback="none specified"):
    """Render a sequence as a comma-separated inline value."""
    cleaned = [inline_text(value, "") for value in (values or [])]
    cleaned = [value for value in cleaned if value]
    return ", ".join(cleaned) if cleaned else fallback


def format_field(label, value):
    """Format one wrapped Markdown bullet without breaking hyphenated terms."""
    prefix = f"- {label}: "
    return textwrap.fill(
        inline_text(value),
        width=WRAP_WIDTH,
        initial_indent=prefix,
        subsequent_indent="  ",
        break_long_words=False,
        break_on_hyphens=False,
    )


def card_label(card):
    """Return the human-readable card label, falling back to the stable ID."""
    return inline_text(card.get("locator"), inline_text(card["card_id"]))


def format_card(card):
    """Render one complete evidence card as structured Markdown."""
    out = [
        f"### {card_label(card)}",
        "",
        format_field("Card ID", f"`{inline_text(card['card_id'])}`"),
        format_field("Category", card.get("category")),
        format_field("Genes", list_text(card.get("genes"))),
        format_field("Disease context", list_text(card.get("diseases"))),
        format_field("Evidence tier", card.get("evidence_tier")),
        format_field("Interpretation", card.get("interpretation")),
        format_field("Source locator", card.get("locator")),
    ]
    if card.get("escalates_to"):
        out.append(format_field("Escalates to", card["escalates_to"]))
    return out


def build_card_reference_map(lines, card_map, sorted_cards):
    """Group cards by identical ordered reference signature.

    Cards with the same (primary_refs, secondary_refs) signature share one
    mapping line. Groups are ordered by the earliest rendered occurrence of any
    member, with card ID as a tie-breaker.
    """
    if not lines:
        return []
    card_by_id = {card["card_id"]: card for card in sorted_cards}
    groups = {}
    for line_index, line in enumerate(lines):
        for member in line["members"]:
            card_id = member["card_id"]
            refs = card_map[card_id]
            signature = (
                tuple(refs["primary_refs"]),
                tuple(refs["secondary_refs"]),
            )
            if signature not in groups:
                groups[signature] = {
                    "card_ids": [card_id],
                    "primary_refs": refs["primary_refs"],
                    "secondary_refs": refs["secondary_refs"],
                    "earliest_line": line_index,
                }
            else:
                if card_id not in groups[signature]["card_ids"]:
                    groups[signature]["card_ids"].append(card_id)
                if line_index < groups[signature]["earliest_line"]:
                    groups[signature]["earliest_line"] = line_index
    for group in groups.values():
        group["card_ids"].sort(key=lambda cid: sort_key(card_by_id[cid]))
    ordered = sorted(
        groups.values(),
        key=lambda group: (group["earliest_line"], group["card_ids"][0]),
    )
    return [
        {
            "card_ids": group["card_ids"],
            "primary_refs": group["primary_refs"],
            "secondary_refs": group["secondary_refs"],
        }
        for group in ordered
    ]


def format_refs(reference_map):
    """Render the terminal card-to-reference mapping section."""
    if not reference_map:
        return ["## Refs", "", "None; no cards were rendered.", ""]
    out = ["## Refs", ""]
    for group in reference_map:
        ids = ",".join(group["card_ids"])
        parts = [
            f"primary ref {','.join(str(number) for number in group['primary_refs'])}"
        ]
        if group["secondary_refs"]:
            parts.append(
                "secondary ref "
                + ",".join(str(number) for number in group["secondary_refs"])
            )
        out.append(f"{ids}: {'; '.join(parts)}")
    out.append("")
    return out


def serialise_card(card):
    """Return the loss-minimising card representation exposed in JSON output."""
    return {
        "card_id": card["card_id"],
        "label": card_label(card),
        "category": card.get("category"),
        "genes": list(card.get("genes") or []),
        "diseases": list(card.get("diseases") or []),
        "evidence_tier": card.get("evidence_tier"),
        "interpretation": card.get("interpretation"),
        "locator": card.get("locator"),
        "escalates_to": card.get("escalates_to"),
        # Retained for compatibility with the previous rendered_facts shape.
        "card_ids": [card["card_id"]],
    }


def render_body(lines):
    out = []
    current_category = None
    rendered_cards = []
    for line in lines:
        card = line["representative"]
        category = card["category"]
        if category != current_category:
            current_category = category
            out.append("")
            out.append(f"## {CATEGORY_HEADINGS.get(category, category)}")
            out.append("")
        out.extend(format_card(card))
        out.append("")
        rendered_cards.append(serialise_card(card))
    return out, rendered_cards


def render_header(bundle):
    provenance = bundle.get("provenance", {})
    adjudication = bundle.get("diagnostic_adjudication", {})
    review = adjudication.get("user_review") or {}
    decision = review.get("decision")
    model_refined = adjudication.get("refined_disease")
    reviewed_refined = bundle.get("refined_disease")
    out = [
        "# Evidence block",
        "",
        textwrap.fill(
            "Collated evidence cards, not a report. Each card below preserves one "
            "retrieved source statement and its card-level metadata; nothing has "
            "been reconciled, ranked clinically or concluded from. Report synthesis "
            "happens downstream.",
            width=WRAP_WIDTH,
        ),
        "",
        f"Genes submitted: {', '.join(bundle.get('genes', [])) or 'none'}",
        f"Provisional major diagnostic category: {bundle.get('provisional_disease')}",
        (
            "Downstream filter disease (adjudicated major category): "
            f"{reviewed_refined}"
        ),
    ]

    model_label = adjudication.get("diagnostic_label")
    reviewed_label = review.get("diagnostic_label")
    if model_label:
        out.append(f"Source-supported diagnostic label: {model_label}")
    if decision == "disagree" and reviewed_label:
        out.append(f"User-reviewed integrated diagnosis: {reviewed_label}")

    status = adjudication.get("status")
    driven_by = adjudication.get("driven_by") or []
    if decision == "disagree":
        out.append(
            "User review revised the downstream diagnosis"
            + (
                f" from {model_refined} to {reviewed_refined}."
                if model_refined != reviewed_refined
                else "."
            )
        )
    elif status == "criteria_met" and model_refined != bundle.get("provisional_disease"):
        out.append(
            "Diagnostic adjudication changed the downstream major category; driven by: "
            + ", ".join(driven_by)
        )
    elif status == "criteria_met":
        suffix = f" Driven by: {', '.join(driven_by)}." if driven_by else ""
        out.append(
            "Diagnostic adjudication: criteria met; major category unchanged."
            + suffix
        )
    elif status == "indeterminate":
        out.append(
            "Diagnostic adjudication: indeterminate; downstream filtering preserves "
            "the provisional major category."
        )
    elif status == "criteria_not_met":
        out.append(
            "Diagnostic adjudication: criteria not met; downstream filtering preserves "
            "the provisional major category."
        )
    else:
        out.append("Diagnostic adjudication metadata is absent.")
    out.append(
        f"Corpus {provenance.get('corpus_version')} "
        f"sha256 {str(provenance.get('corpus_sha256'))[:16]}..., "
        f"retrieved {provenance.get('retrieved_at')}"
    )
    return out


def render_tail(bundle, references, dropped, reference_map):
    out = []
    not_assessed = bundle.get("not_assessed") or []
    out.append("")
    out.append("## Genes not assessed")
    out.append("")
    if not_assessed:
        out.append(textwrap.fill(
            "Submitted, looked for, and absent from this corpus. Not the same thing as "
            "considered and cleared, and the downstream report must say so by name:",
            width=WRAP_WIDTH,
        ))
        out.append("")
        for item in not_assessed:
            out.append(f"- {item['gene']}: {item['reason']}")
    else:
        out.append("None. Every submitted gene is addressed by at least one card.")
    out.append("")
    suppressed = bundle.get("suppressed") or {}
    out.append("## Suppressed by the disease filter")
    out.append("")
    if suppressed.get("count"):
        out.append(textwrap.fill(
            f"{suppressed['count']} gene-matched card(s) withheld because their disease "
            "context does not match the refined disease:",
            width=WRAP_WIDTH,
        ))
        out.append("")
        for disease, count in (suppressed.get("by_disease") or {}).items():
            out.append(f"- {disease}: {count}")
    else:
        out.append(textwrap.fill(
            "None. A persistently empty block here is evidence that branching retrieval "
            "was never needed.",
            width=WRAP_WIDTH,
        ))
    out.append("")
    if dropped:
        out.append("## Truncated")
        out.append("")
        for tier, count in dropped:
            out.append(
                f"- dropped {count} card(s) at evidence tier '{tier}' to fit the budget"
            )
        out.append("")
    out.extend(format_refs(reference_map))
    out.append("## References")
    out.append("")
    for number, entry in enumerate(references, 1):
        suffix = ""
        if entry["citation_incomplete"]:
            suffix = (
                " [citation incomplete in source: "
                + ", ".join(entry["citation_incomplete"])
                + "]"
            )
        wrapped = textwrap.fill(
            f"{number}. {entry['display']}{suffix}",
            width=WRAP_WIDTH,
            subsequent_indent="   ",
        )
        out.append(wrapped)
    if not references:
        out.append("None; no cards were retrieved.")
    return out


def render(bundle, token_budget=DEFAULT_TOKEN_BUDGET):
    cards = list(bundle.get("retrieved", []))
    dropped = []
    while True:
        sorted_cards = sorted(cards, key=sort_key)
        lines = card_lines(sorted_cards)
        references, card_map = assign_references(lines)
        reference_map = build_card_reference_map(lines, card_map, sorted_cards)
        body, rendered_cards = render_body(lines)
        tail = render_tail(bundle, references, dropped, reference_map)
        text = "\n".join(render_header(bundle) + body + tail)
        # Sections are assembled independently, so blank-line runs are joined
        # rather than reasoned about.
        text = re.sub(r"\n{3,}", "\n\n", text).rstrip() + "\n"
        tokens = estimate_tokens(text)
        if tokens <= token_budget:
            over_budget = False
            break
        droppable = [
            tier
            for tier in DROPPABLE_TIERS
            if any(card["evidence_tier"] == tier for card in cards)
        ]
        if not droppable:
            over_budget = True
            break
        tier = droppable[0]
        count = sum(1 for card in cards if card["evidence_tier"] == tier)
        cards = [card for card in cards if card["evidence_tier"] != tier]
        dropped.append((tier, count))
    if over_budget:
        text = text.rstrip() + (
            "\n\nWARNING: this block, before this note, is approximately "
            f"{tokens} tokens against a budget of {token_budget}. Only 'restated "
            "secondary' and 'univariable or descriptive' cards may be dropped, and "
            "both tiers are already gone. Narrow the gene list rather than dropping "
            "guideline criteria.\n"
        )
        tokens = estimate_tokens(text)
    return {
        "text": text,
        "estimated_tokens": tokens,
        "token_budget": token_budget,
        "token_estimate_method": (
            f"characters divided by {CHARS_PER_TOKEN}, rounded up"
        ),
        "over_budget": over_budget,
        "cards_rendered": len(cards),
        "cards_retrieved": len(bundle.get("retrieved", [])),
        "dropped": [
            {"evidence_tier": tier, "cards": count}
            for tier, count in dropped
        ],
        "references": [
            {"number": number, **entry}
            for number, entry in enumerate(references, 1)
        ],
        # Keep the previous key for consumers while changing its unit from a
        # collapsed interpretation to one loss-minimising record per card.
        "rendered_facts": rendered_cards,
        "rendered_cards": rendered_cards,
        "card_reference_map": reference_map,
    }


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--bundle", type=Path, required=True, help="step 4 output")
    parser.add_argument("--token-budget", type=int, default=DEFAULT_TOKEN_BUDGET)
    parser.add_argument("--format", choices=["text", "json"], default="text")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"cannot read bundle: {exc}")

    if bundle.get("step") != 4:
        sys.exit("render expects a step 4 bundle from retrieve.py full")

    result = render(bundle, args.token_budget)
    if args.format == "json":
        payload = json.dumps(result, indent=2, ensure_ascii=False)
    else:
        payload = result["text"]
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            payload if payload.endswith("\n") else payload + "\n",
            encoding="utf-8",
        )
    else:
        print(payload, end="" if payload.endswith("\n") else "\n")
    print(
        f"[render] {result['cards_rendered']}/{result['cards_retrieved']} card(s), "
        f"{len(result['references'])} reference(s), "
        f"~{result['estimated_tokens']} tokens (estimate: "
        f"{result['token_estimate_method']}) against a budget of "
        f"{result['token_budget']}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
