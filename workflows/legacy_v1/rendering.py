"""Legacy-v1 evidence rendering policy."""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

from scripts.core import card_tags
from scripts.core import rendering as core


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
            width=core.WRAP_WIDTH,
        ),
        "",
        f"Genes submitted: {', '.join(bundle.get('genes', [])) or 'none'}",
        f"Provisional major diagnostic category: {bundle.get('provisional_disease')}",
        "Downstream filter disease (adjudicated major category): " f"{reviewed_refined}",
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
            + (f" from {model_refined} to {reviewed_refined}." if model_refined != reviewed_refined else ".")
        )
    elif status == "criteria_met" and model_refined != bundle.get("provisional_disease"):
        out.append(
            "Diagnostic adjudication changed the downstream major category; driven by: "
            + ", ".join(driven_by)
        )
    elif status == "criteria_met":
        suffix = f" Driven by: {', '.join(driven_by)}." if driven_by else ""
        out.append("Diagnostic adjudication: criteria met; major category unchanged." + suffix)
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


def extra_tail(bundle):
    out = ["", "## Genes not assessed", ""]
    not_assessed = bundle.get("not_assessed") or []
    if not_assessed:
        out.append(textwrap.fill(
            "Submitted, looked for, and absent from this corpus. Not the same thing as "
            "considered and cleared, and the downstream report must say so by name:",
            width=core.WRAP_WIDTH,
        ))
        out.append("")
        for item in not_assessed:
            out.append(f"- {item['gene']}: {item['reason']}")
    elif not bundle.get("genes"):
        out.append("None submitted.")
    else:
        out.append("None. Every submitted gene is addressed by at least one card.")
    out.extend(["", "## Suppressed by the disease filter", ""])
    suppressed = bundle.get("suppressed") or {}
    if suppressed.get("count"):
        out.append(textwrap.fill(
            f"{suppressed['count']} gene-matched card(s) withheld because their disease "
            "context matches neither the refined disease nor that category's configured "
            "retrieval_related diseases:",
            width=core.WRAP_WIDTH,
        ))
        out.append("")
        for disease, count in (suppressed.get("by_disease") or {}).items():
            out.append(f"- {disease}: {count}")
    else:
        out.append(textwrap.fill(
            "None. No gene-matched card fell outside the refined disease and its "
            "category-specific retrieval_related scope.",
            width=core.WRAP_WIDTH,
        ))
    out.append("")
    return out


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
    if retrieved_only:
        raise ValueError("legacy-v1 does not support retrieved-only rendering")
    bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
    if bundle.get("step") != 4:
        raise ValueError("render expects a step 4 bundle from retrieve.py")
    if bundle.get("workflow_profile") not in {None, "legacy-v1"}:
        raise ValueError("legacy renderer requires a legacy-v1 bundle")
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
