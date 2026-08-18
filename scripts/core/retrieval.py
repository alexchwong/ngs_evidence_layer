"""Workflow-neutral retrieval/case-boundary primitives."""
from __future__ import annotations

import json
import re
from pathlib import Path

from scripts import vocab
from scripts.core import card_tags

DISEASE_FILTERED = ("diagnosis", "prognosis", "treatment", "biomarker")

def match_genes(card, wanted):
    return sorted({gene.upper() for gene in card["genes"]} & wanted)


def _matches_case_major_category(card, categories):
    """Return the matching broad case-major categories for one evidence card."""
    matched = []
    for category in categories:
        if any(
            vocab.disease_matches_case_major_category(disease, category)
            for disease in card.get("diseases", [])
        ):
            matched.append(category)
    return matched


def step2_card_view(card):
    """Return only diagnosis-card fields needed by the Step-3 model boundary."""
    return {
        "card_id": card["card_id"],
        "genes": list(card.get("genes") or []),
        "diseases": list(card.get("diseases") or []),
        "evidence_tier": card.get("evidence_tier"),
        "interpretation": card.get("interpretation"),
        "paper_nickname": card.get("paper_nickname"),
        "publication_year": card.get("publication_year"),
        "secondary_citation": card.get("secondary_citation"),
    }


def _paper_display(card):
    """Return one deterministic paper label for compact model-facing Markdown."""
    nickname = inline_step_text(card.get("paper_nickname"), fallback="Paper")
    year = card.get("publication_year")
    if year and not re.search(rf"\({re.escape(str(year))}\)$", nickname):
        return f"{nickname} ({year})"
    return nickname


def _group_step_diagnosis_cards(cards):
    """Group diagnosis cards without discarding rich machine-facing metadata."""
    groups = []
    paper_index = {}
    for card in cards:
        paper = _paper_display(card)
        if paper not in paper_index:
            paper_index[paper] = len(groups)
            groups.append({"paper": paper, "tiers": []})
        paper_group = groups[paper_index[paper]]
        tier = inline_step_text(card.get("evidence_tier"))
        tier_group = next((item for item in paper_group["tiers"] if item["tier"] == tier), None)
        if tier_group is None:
            tier_group = {"tier": tier, "diseases": []}
            paper_group["tiers"].append(tier_group)
        diseases = tuple(card.get("diseases") or [])
        disease_group = next((item for item in tier_group["diseases"] if item["key"] == diseases), None)
        if disease_group is None:
            disease_group = {"key": diseases, "cards": []}
            tier_group["diseases"].append(disease_group)
        disease_group["cards"].append(card)
    return groups


def render_step_markdown(result):
    """Render compact model-facing Step-2 Markdown with opaque runtime tags."""
    tag_map = result.get("card_tags") or card_tags.build_card_tags(
        card["card_id"] for card in result.get("diagnosis_cards", [])
    )
    tag_by_id = card_tags.tag_by_id(tag_map)
    lines = [
        "# Step 2 diagnosis evidence",
        "",
        f"- Case major category: {result['case_major_category']}",
        f"- Provisional disease: {result['provisional_disease']}",
        f"- Genes: {', '.join(result['genes']) if result['genes'] else 'none'}",
        f"- Allowed refined diseases: {' | '.join(result['allowed_refined_diseases'])}",
        f"- Genes with no diagnosis card: {', '.join(result['genes_with_no_diagnosis_card']) if result['genes_with_no_diagnosis_card'] else 'none'}",
        "",
        "## Case facts",
        "",
    ]
    for fact in result['case_facts']:
        fact_id = fact['fact_id']
        payload = {k: v for k, v in fact.items() if k != 'fact_id'}
        lines.append(f"- `{fact_id}`: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}")
    if not result['case_facts']:
        lines.append("None.")
    lines.extend(["", "## Diagnosis cards", ""])
    groups = _group_step_diagnosis_cards(result['diagnosis_cards'])
    for paper_group in groups:
        lines.append(f"- Paper: {paper_group['paper']}")
        for tier_group in paper_group['tiers']:
            lines.append(f"  - Evidence tier: {tier_group['tier']}")
            for disease_group in tier_group['diseases']:
                disease_text = " | ".join(disease_group['key']) if disease_group['key'] else "none"
                lines.append(f"    - Diseases: {disease_text}")
                for card in disease_group['cards']:
                    lines.append(
                        f"      - [card:{tag_by_id[card['card_id']]}]: {inline_step_text(card.get('interpretation'))}"
                    )
        lines.append("")
    if not groups:
        lines.append("None.")
    return "\n".join(lines).rstrip() + "\n"


def inline_step_text(value, fallback="not specified"):
    if value is None:
        return fallback
    text = " ".join(str(value).split())
    return text or fallback


def write_step_json(result, path):
    """Persist the rich deterministic Step-2 boundary for downstream scripts."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_step_json(diagnosis_result):
    """Load rich Step-2 JSON, deriving its private sibling from the Markdown path.

    Public workflow commands continue to name ``diagnostic_evidence.md``. Downstream
    code never parses that Markdown; it derives and consumes the sibling JSON.
    """
    path = Path(diagnosis_result)
    json_path = path if path.suffix.lower() == ".json" else path.with_suffix(".json")
    if not json_path.is_file():
        raise ValueError(f"Step-2 machine boundary not found for diagnosis result: {path}")
    try:
        result = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Step-2 machine boundary is not valid JSON: {exc}") from exc
    if not isinstance(result, dict) or result.get("step") != 2:
        raise ValueError("Step-2 machine boundary must be a Step-2 JSON object")
    validate_case_facts(result.get("case_facts"))
    return result


def _field_mismatch_message(label, actual_keys, required_keys):
    actual_keys = set(actual_keys)
    required_keys = set(required_keys)
    missing = sorted(required_keys - actual_keys)
    extra = sorted(actual_keys - required_keys)
    details = []
    if missing:
        details.append("missing field(s): " + ", ".join(missing))
    if extra:
        details.append("unexpected field(s): " + ", ".join(extra))
    return f"{label} has the wrong fields; " + "; ".join(details)


def validate_case_facts(case_facts):
    if not isinstance(case_facts, list):
        raise ValueError("case_facts must be a JSON array")
    fact_ids = []
    for index, fact in enumerate(case_facts):
        if not isinstance(fact, dict):
            raise ValueError(f"case_facts[{index}] must be an object")
        fact_id = fact.get("fact_id")
        if not isinstance(fact_id, str) or not fact_id.strip():
            raise ValueError(f"case_facts[{index}].fact_id must be a non-empty string")
        fact_ids.append(fact_id)
    if len(fact_ids) != len(set(fact_ids)):
        duplicates = sorted({fact_id for fact_id in fact_ids if fact_ids.count(fact_id) > 1})
        raise ValueError(
            "case_facts contains duplicate fact_id value(s): " + ", ".join(duplicates)
            + ". Rename or remove the duplicate entries so every case fact has a unique fact_id."
        )
    return case_facts


def _normalise_genes(genes, *, field="genes"):
    if not isinstance(genes, list):
        raise ValueError(f"{field} must be a JSON array")
    normalised = []
    seen = set()
    for index, value in enumerate(genes):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field}[{index}] must be a non-empty string")
        upper = value.upper()
        if upper in seen:
            raise ValueError(f"{field} contains duplicate gene {upper!r} after normalisation")
        seen.add(upper)
        normalised.append(upper)
    return normalised


def _validate_case_disease(disease, genes, *, field):
    """Validate one case-level disease against the submitted variant genes.
    ``no_haematological_malignancy`` is deliberately case-only and is legal only
    when no variant genes are submitted. Other diseases may also have no reported
    variants; the case-only term must not be inferred solely from an empty gene list.
    """
    if disease not in vocab.CASE_DISEASE_SET:
        raise ValueError(
            f"{field} has invalid value {disease!r}. Use an exact canonical disease value "
            "from the allowed refined diseases supplied in diagnostic_evidence.md."
        )
    if disease == vocab.NO_HAEMATOLOGICAL_MALIGNANCY and genes:
        raise ValueError(
            f"{field} {vocab.NO_HAEMATOLOGICAL_MALIGNANCY!r} requires no reported variants"
        )
    return disease


def _validate_case_major_category(category, genes, *, field="case_major_category"):
    if category not in vocab.CASE_MAJOR_CATEGORY_SET:
        raise ValueError(
            f"{field} has invalid value {category!r}. Replace it with exactly one allowed "
            "case-major category from case-major-categories.json; do not invent a new category."
        )
    if category == vocab.NO_HAEMATOLOGICAL_MALIGNANCY and genes:
        raise ValueError(
            f"{field} {vocab.NO_HAEMATOLOGICAL_MALIGNANCY!r} requires no reported variants"
        )
    return category


def validate_case_input(path):
    """Validate Step-1 case input without normalising its provisional diagnosis."""
    if not path.is_file():
        raise ValueError(f"case-input not found: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"case-input is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("case-input must be a JSON object")
    required = {"case_major_category", "provisional_disease", "genes", "case_facts"}
    if set(document) != required:
        raise ValueError(
            _field_mismatch_message("case-input.json", document.keys(), required)
            + ". Edit case-input.json so it contains exactly: " + ", ".join(sorted(required))
        )
    provisional_disease = document["provisional_disease"]
    if not isinstance(provisional_disease, str) or not provisional_disease.strip():
        raise ValueError("case-input provisional_disease must be a non-empty string")
    genes = _normalise_genes(document["genes"], field="case-input genes")
    case_major_category = _validate_case_major_category(
        document["case_major_category"], genes, field="case-input case_major_category"
    )
    case_facts = validate_case_facts(document["case_facts"])
    return {
        "case_major_category": case_major_category,
        "provisional_disease": provisional_disease.strip(),
        "genes": genes,
        "case_facts": case_facts,
    }


def _infer_case_major_category_from_provisional(provisional_disease):
    """Backward-compatible inference for direct callers, never used for case-input."""
    canonical = vocab.canonical_case_disease(provisional_disease)
    if canonical is None:
        return None
    return vocab.preferred_case_major_category(canonical)
