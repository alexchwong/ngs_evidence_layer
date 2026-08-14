#!/usr/bin/env python3
"""Render a step 4 retrieval bundle as a structured evidence-card block.
Quotes are never rendered or returned by retrieval; they remain private inside
accepted ingestion packages.
The rendered Markdown groups cards by category, paper, evidence tier and disease.
Only the interpretation and an opaque runtime card-tag marker are repeated per card; rich
card metadata remains in the deterministic JSON representation.
Citations remain publication-style at the end of the block. Each card exposes
its private stable card ID internally; model-facing ``evidence.md`` replaces those IDs with opaque runtime tags, and ``## Refs`` maps tags to primary and
secondary references, and ``## References`` contains the numbered bibliography.
Citation numbering is scripted rather than modelled. Numbers fall out of the
deterministic card order, so the same corpus and case produce the same block,
and every number points at a reference contributed by a rendered card.
Paper order follows first appearance in the historical deterministic card order;
within each paper, evidence tier, disease tuple and stable card order are deterministic.
Usage:
  render.py --bundle bundle.json > evidence.md
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
import card_tags  # noqa: E402
DEFAULT_TOKEN_BUDGET = 120_000
CHARS_PER_TOKEN = 4  # estimate; stated as an estimate wherever it is reported
WRAP_WIDTH = 78
# Truncation order. Guideline criteria and multivariable-adjusted findings are
# never dropped: if the block still will not fit after these two tiers are gone,
# the honest output is an over-budget block with a warning, not a quietly
# weakened one.
DROPPABLE_TIERS = ["restated secondary", "univariable or descriptive"]
CATEGORY_HEADINGS = {
    "diagnosis": "Diagnosis Cards",
    "prognosis": "Prognosis Cards",
    "treatment": "Treatment Cards",
    "biomarker": "Biomarker Cards",
    "germline": "Germline Cards",
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

def card_label(card):
    """Return the human-readable card label, falling back to the stable ID."""
    return inline_text(card.get("locator"), inline_text(card["card_id"]))


def paper_display(card):
    """Return a compact deterministic paper label including year when available."""
    nickname = inline_text(card.get("paper_nickname"), "Paper")
    year = card.get("publication_year")
    if year and not re.search(rf"\({re.escape(str(year))}\)$", nickname):
        return f"{nickname} ({year})"
    return nickname


def _paper_key(card):
    return card.get("publication_key") or (
        card.get("paper_nickname"), card.get("publication_year"), card.get("citation_display")
    )


def group_cards_for_render(sorted_cards):
    """Group cards as category -> paper -> tier -> diseases -> cards.

    Category and paper order follow first appearance in the historical deterministic
    sort. Within each paper, evidence tier and disease grouping are deterministic.
    Returns both groups and the exact flattened rendered card order.
    """
    categories = []
    category_index = {}
    for card in sorted_cards:
        category = card["category"]
        if category not in category_index:
            category_index[category] = len(categories)
            categories.append({"category": category, "papers": [], "paper_index": {}})
        category_group = categories[category_index[category]]
        key = _paper_key(card)
        if key not in category_group["paper_index"]:
            category_group["paper_index"][key] = len(category_group["papers"])
            category_group["papers"].append({"display": paper_display(card), "cards": []})
        category_group["papers"][category_group["paper_index"][key]]["cards"].append(card)

    render_order = []
    for category_group in categories:
        category_group.pop("paper_index", None)
        for paper_group in category_group["papers"]:
            paper_cards = sorted(
                paper_group.pop("cards"),
                key=lambda card: (
                    vocab.TIER_RANK.get(card.get("evidence_tier"), len(vocab.TIER_RANK)),
                    tuple(card.get("diseases") or []),
                    sort_key(card),
                ),
            )
            tiers = []
            tier_index = {}
            for card in paper_cards:
                tier = inline_text(card.get("evidence_tier"))
                if tier not in tier_index:
                    tier_index[tier] = len(tiers)
                    tiers.append({"tier": tier, "diseases": [], "disease_index": {}})
                tier_group = tiers[tier_index[tier]]
                diseases = tuple(card.get("diseases") or [])
                if diseases not in tier_group["disease_index"]:
                    tier_group["disease_index"][diseases] = len(tier_group["diseases"])
                    tier_group["diseases"].append({"diseases": diseases, "cards": []})
                tier_group["diseases"][tier_group["disease_index"][diseases]]["cards"].append(card)
                render_order.append(card)
            for tier_group in tiers:
                tier_group.pop("disease_index", None)
            paper_group["tiers"] = tiers
    return categories, render_order

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
        "retrieval_match": card.get("retrieval_match"),
        "matched_retrieval_related_diseases": list(
            card.get("matched_retrieval_related_diseases") or []
        ),
        "evidence_tier": card.get("evidence_tier"),
        "interpretation": card.get("interpretation"),
        "locator": card.get("locator"),
        # Retained for compatibility with the previous rendered_facts shape.
        "card_ids": [card["card_id"]],
    }

def render_body(groups):
    out = []
    rendered_cards = []
    for category_group in groups:
        category = category_group["category"]
        out.extend(["", f"## {CATEGORY_HEADINGS.get(category, category)}", ""])
        for paper_number, paper_group in enumerate(category_group["papers"], 1):
            out.append(f"{paper_number}. Paper: {paper_group['display']}")
            out.append("")
            for tier_group in paper_group["tiers"]:
                out.append(f"- Evidence tier: {tier_group['tier']}")
                for disease_group in tier_group["diseases"]:
                    diseases = " | ".join(disease_group["diseases"]) if disease_group["diseases"] else "none"
                    disease_label = (
                        "Disease context"
                        if len(disease_group["diseases"]) <= 1
                        else "Diseases"
                    )
                    out.append(f"  - {disease_label}: {diseases}")
                    for card in disease_group["cards"]:
                        out.append(
                            f"    - [card:{inline_text(card['card_id'])}]: "
                            f"{inline_text(card.get('interpretation'))}"
                        )
                        rendered_cards.append(serialise_card(card))
            out.append("")
    return out, rendered_cards

def render_header(bundle):
    provenance = bundle.get("provenance", {})
    adjudication = bundle.get("diagnostic_adjudication", {})
    review = adjudication.get("user_review")
    if review == "automatic":
        decision = "automatic"
        reviewed_label = None
    else:
        review = review or {}
        decision = review.get("decision")
        reviewed_label = review.get("diagnostic_label")
    model_refined = adjudication.get("refined_disease")
    reviewed_refined = bundle.get("refined_disease")
    out = [
        "# Evidence block",
        "",
        textwrap.fill(
            "Collated evidence cards, not a report. Source, evidence tier and disease "
            "context are grouped above each card interpretation; report synthesis happens "
            "downstream.",
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
    elif not bundle.get("genes"):
        out.append("None submitted.")
    else:
        out.append("None. Every submitted gene is addressed by at least one card.")
    out.append("")
    suppressed = bundle.get("suppressed") or {}
    out.append("## Suppressed by the disease filter")
    out.append("")
    if suppressed.get("count"):
        out.append(textwrap.fill(
            f"{suppressed['count']} gene-matched card(s) withheld because their disease "
            "context matches neither the refined disease nor that category's configured "
            "retrieval_related diseases:",
            width=WRAP_WIDTH,
        ))
        out.append("")
        for disease, count in (suppressed.get("by_disease") or {}).items():
            out.append(f"- {disease}: {count}")
    else:
        out.append(textwrap.fill(
            "None. No gene-matched card fell outside the refined disease and its "
            "category-specific retrieval_related scope.",
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
    # evidence.md is the complete model-facing boundary: preserve every diagnosis
    # card seen in Step 2, then add Step-4 retrieval, deduplicated by stable ID.
    cards_by_id = {}
    for card in list(bundle.get("diagnostic_context", [])) + list(bundle.get("retrieved", [])):
        cards_by_id.setdefault(card["card_id"], card)
    cards = list(cards_by_id.values())
    dropped = []
    while True:
        sorted_cards = sorted(cards, key=sort_key)
        groups, rendered_order = group_cards_for_render(sorted_cards)
        lines = card_lines(rendered_order)
        references, card_map = assign_references(lines)
        reference_map = build_card_reference_map(lines, card_map, rendered_order)
        body, rendered_cards = render_body(groups)
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
        "cards_available": len(cards_by_id),
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



def build_card_tags(rendered_cards):
    """Backward-compatible wrapper around the shared runtime-tag utility."""
    return card_tags.build_card_tags(card["card_id"] for card in rendered_cards)


def evidence_markdown(result, tag_map):
    """Render the single model-facing evidence Markdown using runtime card tags."""
    tag_by_id = {row["card_id"]: row["card_tag"] for row in tag_map["tags"]}
    lines = result["text"].splitlines()
    rendered = []
    in_refs = False
    for line in lines:
        if line == "# Evidence block":
            rendered.append("# Evidence")
            continue
        if line == "## Refs":
            in_refs = True
            rendered.append(line)
            continue
        if in_refs and line and ": primary ref " in line:
            card_text, rest = line.split(": ", 1)
            tags = []
            for card_id in card_text.split(","):
                if card_id not in tag_by_id:
                    raise ValueError(f"rendered reference mapping names unknown card {card_id}")
                tags.append(tag_by_id[card_id])
            rendered.append(f"{','.join(tags)}: {rest}")
            continue
        for card_id, tag in tag_by_id.items():
            line = line.replace(f"[card:{card_id}]", f"[card:{tag}]")
            if line == f"### {card_id}":
                line = f"### Card {tag}"
            # Stable IDs may also occur in deterministic diagnostic-summary text
            # (for example "Driven by"). Never expose them model-side.
            line = line.replace(card_id, tag)
        rendered.append(line)
    return "\n".join(rendered).rstrip() + "\n"

def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--bundle", type=Path, required=True, help="step 4 output")
    parser.add_argument("--token-budget", type=int, default=DEFAULT_TOKEN_BUDGET)
    parser.add_argument("--output", type=Path, help="write evidence.md")
    parser.add_argument(
        "--card-tag-output",
        type=Path,
        help="write runtime card-tag to stable-card-ID deconvolution JSON",
    )
    args = parser.parse_args()
    try:
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        sys.exit(f"cannot read bundle: {exc}")
    if bundle.get("step") != 4:
        sys.exit("render expects a step 4 bundle from retrieve.py full")
    result = render(bundle, args.token_budget)
    global_tag_map = bundle.get("runtime_card_tags")
    if not global_tag_map:
        # Backward-compatible direct renderer use. New workflow bundles always
        # persist the eligibility-universe map so Step 2 and Step 5 tags agree.
        global_tag_map = card_tags.build_card_tags(
            card["card_id"] for card in result["rendered_cards"]
        )
    tag_map = card_tags.subset_tag_map(
        global_tag_map, [card["card_id"] for card in result["rendered_cards"]]
    )
    payload = evidence_markdown(result, tag_map)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    if args.card_tag_output:
        args.card_tag_output.parent.mkdir(parents=True, exist_ok=True)
        args.card_tag_output.write_text(
            json.dumps(tag_map, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    print(
        f"[render] {result['cards_rendered']}/{result['cards_available']} model-facing card(s) rendered "
        f"({result['cards_retrieved']} Step-4 retrieved), "
        f"{len(result['references'])} reference(s), "
        f"~{result['estimated_tokens']} tokens (estimate: "
        f"{result['token_estimate_method']}) against a budget of "
        f"{result['token_budget']}",
        file=sys.stderr,
    )

if __name__ == "__main__":
    main()
