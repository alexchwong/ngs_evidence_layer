#!/usr/bin/env python3
"""Deterministic diagnosis and full-evidence retrieval.

Step 2 uses the Step-1 ``case_major_category`` for broad diagnosis recall. A
diagnosis card is eligible when it belongs to that major category, is linked by an
existing diagnosis ``retrieval_related`` rule, or matches a submitted gene. Gene
matching therefore remains disease-unrestricted and can still escape an incorrect
provisional category.

Step 4 carries forward only diagnosis cards actually used in adjudication. For
prognosis, treatment and biomarker evidence it retains the narrower gene + refined
-disease/``retrieval_related`` rule; when adjudication remains indeterminate or at
the original broad major category, the disease side may fall back to that major
category. Germline remains gene-only.
"""
import argparse
import hashlib
import json
import re
import sys

import yaml
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import vocab  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CORPUS = REPO_ROOT / "output/corpus/nel.corpus.json"
DEFAULT_INDEX = REPO_ROOT / "output/corpus/nel.index.json"
DEFAULT_BLACKLIST = REPO_ROOT / "output/corpus/blacklist.yaml"
CARD_CATEGORIES = {"diagnosis", "prognosis", "treatment", "biomarker", "germline"}
DISEASE_FILTERED = ("diagnosis", "prognosis", "treatment", "biomarker")

def canonical_bytes(document):
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()

def load_corpus(corpus_path, index_path):
    """Load the corpus and refuse a stale index.
    A mismatched index means the postings and the cards disagree about what
    exists. Retrieval built on that is not wrong in an obvious way; it is wrong in
    a way that looks like an absence of evidence.
    """
    corpus = json.loads(Path(corpus_path).read_text(encoding="utf-8"))
    index = json.loads(Path(index_path).read_text(encoding="utf-8"))
    digest = hashlib.sha256(canonical_bytes(corpus)).hexdigest()
    if index.get("corpus_sha256") != digest:
        raise ValueError(
            f"index does not match corpus: corpus hashes to {digest}, index claims "
            f"{index.get('corpus_sha256')}. Rebuild before retrieving."
        )
    return corpus, index, digest

def flatten(corpus):
    """One record per card, carrying what render needs and nothing more."""
    cards = []
    for publication in corpus.get("publications", []):
        document = publication.get("document", {})
        citation = document.get("citation", {})
        for card in document.get("cards", []):
            cards.append({
                "card_id": card["card_id"],
                "category": card["category"],
                "genes": list(card.get("genes", [])),
                "diseases": list(card.get("diseases") or []),
                "evidence_tier": card["evidence_tier"],
                "interpretation": card["interpretation"],
                "locator": card["locator"],
                "publication_key": document.get("publication_key"),
                "paper_nickname": document.get("paper_nickname"),
                "publication_year": citation.get("year"),
                "citation_display": citation.get("display"),
                "citation_incomplete": citation.get("citation_incomplete") or [],
                "secondary_citation": card.get("secondary_citation"),
            })
    return cards

def match_genes(card, wanted):
    return sorted({gene.upper() for gene in card["genes"]} & wanted)


def _blacklist_string_list(value, *, field, uppercase=False):
    """Validate one include/exclude list and return normalised unique values."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"blacklist {field} must be a YAML list")
    result = []
    seen = set()
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"blacklist {field}[{index}] must be a non-empty string")
        item = item.strip().upper() if uppercase else item.strip()
        if item in seen:
            raise ValueError(f"blacklist {field} contains duplicate value {item!r}")
        seen.add(item)
        result.append(item)
    return result


def _normalise_blacklist_dimension(value, *, field, uppercase=False, allowed=None):
    if value is None:
        value = {}
    if not isinstance(value, dict) or set(value) - {"include", "exclude"}:
        raise ValueError(
            f"blacklist {field} must contain only optional include/exclude lists"
        )
    include = _blacklist_string_list(
        value.get("include", []), field=f"{field}.include", uppercase=uppercase
    )
    exclude = _blacklist_string_list(
        value.get("exclude", []), field=f"{field}.exclude", uppercase=uppercase
    )
    overlap = sorted(set(include) & set(exclude))
    if overlap:
        raise ValueError(
            f"blacklist {field} includes and excludes the same value(s): "
            + ", ".join(overlap)
        )
    if allowed is not None:
        unknown = sorted((set(include) | set(exclude)) - set(allowed))
        if unknown:
            raise ValueError(
                f"blacklist {field} contains unknown value(s): " + ", ".join(unknown)
            )
    return {"include": include, "exclude": exclude}


def _normalise_blacklist_rule(value, *, field):
    if value is None:
        value = {}
    if not isinstance(value, dict):
        raise ValueError(f"blacklist {field} must be a mapping")
    unknown = set(value) - {"enabled", "categories", "genes", "cards"}
    if unknown:
        raise ValueError(
            f"blacklist {field} contains unsupported key(s): " + ", ".join(sorted(unknown))
        )
    enabled = value.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError(f"blacklist {field}.enabled must be true or false")
    return {
        "enabled": enabled,
        "categories": _normalise_blacklist_dimension(
            value.get("categories"), field=f"{field}.categories", allowed=CARD_CATEGORIES
        ),
        "genes": _normalise_blacklist_dimension(
            value.get("genes"), field=f"{field}.genes", uppercase=True
        ),
        "cards": _normalise_blacklist_dimension(
            value.get("cards"), field=f"{field}.cards"
        ),
    }


def load_blacklist(path, cards):
    """Load and validate the optional card-eligibility policy.

    Missing files are intentionally equivalent to an enabled empty policy so old
    deployments keep their historical retrieval behaviour.
    """
    path = Path(path)
    if not path.is_file():
        return {
            "enabled": True,
            "global": _normalise_blacklist_rule({}, field="global"),
            "papers": {},
            "path": str(path),
            "present": False,
        }
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"blacklist YAML is invalid: {exc}") from exc
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        raise ValueError("blacklist root must be a YAML mapping")
    unknown = set(raw) - {"enabled", "global", "papers"}
    if unknown:
        raise ValueError(
            "blacklist contains unsupported top-level key(s): " + ", ".join(sorted(unknown))
        )
    enabled = raw.get("enabled", True)
    if not isinstance(enabled, bool):
        raise ValueError("blacklist enabled must be true or false")
    global_rule = _normalise_blacklist_rule(raw.get("global"), field="global")
    papers_raw = raw.get("papers") or {}
    if not isinstance(papers_raw, dict):
        raise ValueError("blacklist papers must be a mapping keyed by publication_key")

    publication_cards = {}
    all_card_ids = set()
    for card in cards:
        publication_cards.setdefault(card["publication_key"], set()).add(card["card_id"])
        all_card_ids.add(card["card_id"])

    papers = {}
    for publication_key, rule_raw in papers_raw.items():
        if not isinstance(publication_key, str) or not publication_key.strip():
            raise ValueError("blacklist paper keys must be non-empty publication_key strings")
        publication_key = publication_key.strip()
        if publication_key not in publication_cards:
            raise ValueError(f"blacklist names unknown publication_key {publication_key!r}")
        rule = _normalise_blacklist_rule(rule_raw, field=f"papers.{publication_key}")
        named_cards = set(rule["cards"]["include"]) | set(rule["cards"]["exclude"])
        wrong_cards = sorted(named_cards - publication_cards[publication_key])
        if wrong_cards:
            raise ValueError(
                f"blacklist papers.{publication_key}.cards names card(s) not in that paper: "
                + ", ".join(wrong_cards)
            )
        papers[publication_key] = rule

    global_named_cards = (
        set(global_rule["cards"]["include"]) | set(global_rule["cards"]["exclude"])
    )
    unknown_cards = sorted(global_named_cards - all_card_ids)
    if unknown_cards:
        raise ValueError(
            "blacklist global.cards names unknown card(s): " + ", ".join(unknown_cards)
        )
    return {
        "enabled": enabled,
        "global": global_rule,
        "papers": papers,
        "path": str(path),
        "present": True,
    }


def _dimension_allows(card, dimension, values):
    include = set(dimension["include"])
    exclude = set(dimension["exclude"])
    if isinstance(values, str):
        values = {values}
    else:
        values = set(values)
    if exclude & values:
        return False
    if include and not (include & values):
        return False
    return True


def _rule_allows(card, rule):
    if not rule["enabled"]:
        return False
    if not _dimension_allows(card, rule["categories"], card["category"]):
        return False
    genes = {gene.upper() for gene in card.get("genes") or []}
    if not _dimension_allows(card, rule["genes"], genes):
        return False
    if not _dimension_allows(card, rule["cards"], card["card_id"]):
        return False
    return True


def apply_blacklist(cards, config):
    """Return cards permitted by global AND paper-specific policy rules."""
    if not config["enabled"]:
        return list(cards), []
    allowed = []
    excluded = []
    for card in cards:
        paper_rule = config["papers"].get(card["publication_key"])
        permitted = _rule_allows(card, config["global"])
        if permitted and paper_rule is not None:
            permitted = _rule_allows(card, paper_rule)
        (allowed if permitted else excluded).append(card)
    return allowed, excluded


def blacklist_cards(cards, path):
    config = load_blacklist(path, cards)
    allowed, excluded = apply_blacklist(cards, config)
    if config["present"] and config["enabled"]:
        print(
            f"[retrieve] blacklist excluded {len(excluded)} of {len(cards)} cards "
            f"({config['path']})",
            file=sys.stderr,
        )
    elif config["present"]:
        print(f"[retrieve] blacklist disabled ({config['path']})", file=sys.stderr)
    return allowed


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
    """Render compact model-facing Step-2 Markdown; JSON remains authoritative."""
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
                        f"      - [{card['card_id']}]: {inline_step_text(card.get('interpretation'))}"
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

def provenance(corpus, corpus_path, index_path, digest, card_ids):
    return {
        "corpus_version": corpus.get("corpus_version"),
        "corpus_generated_at": corpus.get("generated_at"),
        "corpus_sha256": digest,
        "corpus_path": str(corpus_path),
        "index_path": str(index_path),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "card_ids": sorted(card_ids),
    }

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
        raise ValueError("case fact IDs must be unique")
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
        raise ValueError(f"{field} {disease!r} is outside the case disease vocabulary")
    if disease == vocab.NO_HAEMATOLOGICAL_MALIGNANCY and genes:
        raise ValueError(
            f"{field} {vocab.NO_HAEMATOLOGICAL_MALIGNANCY!r} requires no reported variants"
        )
    return disease

def _validate_case_major_category(category, genes, *, field="case_major_category"):
    if category not in vocab.CASE_MAJOR_CATEGORY_SET:
        raise ValueError(f"{field} {category!r} is outside the case-major-category vocabulary")
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
            "case-input must contain exactly: " + ", ".join(sorted(required))
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


def step2(
    cards, genes, provisional_disease, case_facts=None, *, case_major_category=None
):
    case_facts = validate_case_facts(case_facts or [])
    normalised_genes = _normalise_genes(list(genes), field="genes")
    if not isinstance(provisional_disease, str) or not provisional_disease.strip():
        raise ValueError("provisional_disease must be a non-empty string")
    if case_major_category is None:
        case_major_category = _infer_case_major_category_from_provisional(provisional_disease)
        if case_major_category is None:
            raise ValueError(
                "case_major_category is required when provisional_disease is not an exact canonical disease or alias"
            )
    _validate_case_major_category(case_major_category, normalised_genes)
    wanted = set(normalised_genes)
    related_diseases = set(
        vocab.retrieval_related_diseases(case_major_category, "diagnosis")
        if case_major_category in vocab.DISEASE_SET else []
    )
    hits = []
    for card in cards:
        if card["category"] != "diagnosis":
            continue
        matched = match_genes(card, wanted)
        diseases = set(card["diseases"])
        major_category_matched = any(
            vocab.disease_matches_case_major_category(disease, case_major_category)
            for disease in diseases
        )
        related_matches = sorted(diseases & related_diseases)
        if not matched and not major_category_matched and not related_matches:
            continue
        hit = dict(card)
        hit["matched_genes"] = matched
        if major_category_matched:
            hit["matched_case_major_category"] = case_major_category
        if related_matches:
            hit["matched_retrieval_related_diseases"] = related_matches
        hits.append(hit)

    represented = {
        disease
        for hit in hits
        for disease in hit.get("diseases", [])
        if disease in vocab.DISEASE_SET
    }
    allowed = [disease for disease in vocab.DISEASES if disease in represented]
    if case_major_category in vocab.CASE_DISEASE_SET and case_major_category not in allowed:
        allowed.insert(0, case_major_category)
    if not allowed:
        # Every normal case-major category is a canonical or case-only routing value;
        # this guard makes malformed future vocabulary fail clearly.
        raise ValueError(
            f"case_major_category {case_major_category!r} provides no allowed refined disease"
        )
    genes_with_diagnosis_card = {gene for hit in hits for gene in hit["matched_genes"]}
    return {
        "step": 2,
        "case_major_category": case_major_category,
        "provisional_disease": provisional_disease.strip(),
        "genes": sorted(wanted),
        "case_facts": case_facts,
        "diagnosis_cards": [
            step2_card_view(hit)
            for hit in sorted(hits, key=lambda item: item["card_id"])
        ],
        "allowed_refined_diseases": allowed,
        "genes_with_no_diagnosis_card": sorted(wanted - genes_with_diagnosis_card),
    }


def _validate_user_review(
    adjudication, genes, allowed_refined_diseases, retrieved_card_ids, *,
    require_completed_review
):
    """Validate automatic or manual Step 3 review state."""
    review = adjudication.get("user_review")
    model_refined = adjudication["refined_disease"]
    model_label = adjudication["diagnostic_label"]
    downstream = adjudication["downstream_filter_disease"]

    if review == "automatic":
        if downstream != model_refined:
            raise ValueError(
                "automatic user_review requires downstream_filter_disease to exactly "
                "equal refined_disease"
            )
        return review

    if review is None:
        if require_completed_review:
            raise ValueError("user_review is required before Step 4")
        if downstream != model_refined:
            raise ValueError(
                "without user_review, downstream_filter_disease must exactly equal "
                "refined_disease"
            )
        return None

    review_keys = {"decision", "diagnostic_label", "refined_disease", "reason", "card_ids"}
    if not isinstance(review, dict) or set(review) != review_keys:
        raise ValueError(
            "user_review must be 'automatic' or contain exactly: "
            + ", ".join(sorted(review_keys))
        )
    decision = review["decision"]
    if decision not in {"pending", "agree", "disagree"}:
        raise ValueError(f"invalid user_review decision {decision!r}")
    reviewed_label = review["diagnostic_label"]
    if reviewed_label is not None and (
        not isinstance(reviewed_label, str) or not reviewed_label.strip()
    ):
        raise ValueError(
            "user_review diagnostic_label must be null or a non-empty string"
        )
    reviewed_refined = review["refined_disease"]
    if reviewed_refined is not None:
        _validate_case_disease(
            reviewed_refined,
            genes,
            field="user_review refined_disease",
        )
        if reviewed_refined not in allowed_refined_diseases:
            raise ValueError(
                f"user_review refined_disease {reviewed_refined!r} is not allowed by Step 2"
            )
    reviewed_reason = review["reason"]
    reviewed_cards = review["card_ids"]
    if reviewed_reason is not None and (
        not isinstance(reviewed_reason, str) or not reviewed_reason.strip()
    ):
        raise ValueError("user_review reason must be null or a non-empty string")
    if not isinstance(reviewed_cards, list) or any(
        not isinstance(card_id, str) or not card_id for card_id in reviewed_cards
    ):
        raise ValueError("user_review card_ids must be an array of non-empty strings")
    if len(reviewed_cards) != len(set(reviewed_cards)):
        raise ValueError("user_review card_ids must be unique")
    if any(card_id not in retrieved_card_ids for card_id in reviewed_cards):
        raise ValueError("every user_review card_id must name a retrieved diagnosis card")

    if decision == "pending":
        if (
            reviewed_label is not None
            or reviewed_refined is not None
            or reviewed_reason is not None
            or reviewed_cards
        ):
            raise ValueError(
                "pending user_review must have null diagnostic_label, refined_disease, "
                "and reason, with empty card_ids"
            )
        if downstream != model_refined:
            raise ValueError(
                "pending user_review must preserve the model refined_disease as the "
                "downstream_filter_disease"
            )
        if require_completed_review:
            raise ValueError("user review is pending; Step 4 is blocked")
        return review
    if reviewed_refined is None:
        raise ValueError("completed user_review requires refined_disease")
    if downstream != reviewed_refined:
        raise ValueError(
            "downstream_filter_disease must exactly equal user_review.refined_disease"
        )
    if decision == "agree":
        if (
            reviewed_refined != model_refined
            or reviewed_label != model_label
            or reviewed_reason != adjudication["reason"]
            or reviewed_cards != adjudication["driven_by"]
        ):
            raise ValueError(
                "an agreeing user_review must copy the model diagnostic_label, "
                "refined_disease, reason, and driven_by cards exactly"
            )
    else:
        if reviewed_label is None:
            raise ValueError(
                "a disagreeing user_review requires the user's integrated diagnostic_label"
            )
        if reviewed_reason is None or not reviewed_cards:
            raise ValueError(
                "a disagreeing user_review requires an evidence-grounded reason and card_ids"
            )
    return review

def validate_adjudication(step2_result, adjudication, *, require_completed_review=False):
    base_keys = {
        "status", "provisional_disease", "refined_disease",
        "downstream_filter_disease", "diagnostic_label", "driven_by",
        "criterion_assessment", "reason",
    }
    allowed_key_sets = {frozenset(base_keys), frozenset(base_keys | {"user_review"})}
    if not isinstance(adjudication, dict) or frozenset(adjudication) not in allowed_key_sets:
        raise ValueError(
            "adjudication must contain exactly the model fields and optional user_review: "
            + ", ".join(sorted(base_keys | {"user_review"}))
        )
    status = adjudication["status"]
    if status not in {"criteria_met", "criteria_not_met", "indeterminate"}:
        raise ValueError(f"invalid adjudication status {status!r}")
    provisional = step2_result["provisional_disease"]
    if not isinstance(provisional, str) or not provisional.strip():
        raise ValueError("step2 provisional_disease must be a non-empty string")
    genes = _normalise_genes(step2_result["genes"], field="step2 genes")
    case_major_category = step2_result.get("case_major_category")
    _validate_case_major_category(case_major_category, genes, field="step2 case_major_category")
    allowed_refined_diseases = step2_result.get("allowed_refined_diseases", [])
    if not isinstance(allowed_refined_diseases, list) or any(
        disease not in vocab.CASE_DISEASE_SET for disease in allowed_refined_diseases
    ):
        raise ValueError("step2 allowed_refined_diseases is invalid")
    if adjudication["provisional_disease"] != provisional:
        raise ValueError("adjudication provisional_disease does not match diagnosis result")
    refined = adjudication["refined_disease"]
    _validate_case_disease(refined, genes, field="adjudication refined_disease")
    if refined not in allowed_refined_diseases:
        raise ValueError(
            f"adjudication refined_disease {refined!r} is not allowed by Step 2"
        )
    downstream = adjudication["downstream_filter_disease"]
    _validate_case_disease(
        downstream,
        genes,
        field="adjudication downstream_filter_disease",
    )
    if downstream not in allowed_refined_diseases:
        raise ValueError(
            f"adjudication downstream_filter_disease {downstream!r} is not allowed by Step 2"
        )
    label = adjudication["diagnostic_label"]
    if label is not None and (not isinstance(label, str) or not label.strip()):
        raise ValueError("diagnostic_label must be null or a non-empty string")
    if not isinstance(adjudication["reason"], str) or not adjudication["reason"].strip():
        raise ValueError("adjudication reason must be a non-empty string")
    retrieved_card_ids = {card["card_id"] for card in step2_result["diagnosis_cards"]}
    driven_by = adjudication["driven_by"]
    if not isinstance(driven_by, list) or any(card_id not in retrieved_card_ids for card_id in driven_by):
        raise ValueError("every driven_by ID must name a retrieved diagnosis card")
    if len(driven_by) != len(set(driven_by)):
        raise ValueError("driven_by card IDs must be unique")
    supplied_fact_ids = {fact["fact_id"] for fact in validate_case_facts(step2_result["case_facts"])}
    assessments = adjudication["criterion_assessment"]
    if not isinstance(assessments, list):
        raise ValueError("criterion_assessment must be an array")
    required_assessments = []
    for index, item in enumerate(assessments):
        item_keys = {"criterion", "required", "status", "card_ids", "case_fact_ids"}
        if not isinstance(item, dict) or set(item) != item_keys:
            raise ValueError(f"criterion_assessment[{index}] has the wrong fields")
        if not isinstance(item["criterion"], str) or not item["criterion"].strip():
            raise ValueError(f"criterion_assessment[{index}].criterion must be non-empty")
        if not isinstance(item["required"], bool):
            raise ValueError(f"criterion_assessment[{index}].required must be boolean")
        if item["status"] not in {"met", "not_met", "unknown"}:
            raise ValueError(f"criterion_assessment[{index}] has invalid status")
        if not isinstance(item["card_ids"], list) or not item["card_ids"]:
            raise ValueError(f"criterion_assessment[{index}] must cite a diagnosis card")
        if any(card_id not in retrieved_card_ids for card_id in item["card_ids"]):
            raise ValueError(f"criterion_assessment[{index}] cites an unretrieved card")
        if not isinstance(item["case_fact_ids"], list):
            raise ValueError(f"criterion_assessment[{index}].case_fact_ids must be an array")
        if any(fact_id not in supplied_fact_ids for fact_id in item["case_fact_ids"]):
            raise ValueError(f"criterion_assessment[{index}] cites an unsupplied case fact")
        if item["status"] != "unknown" and not item["case_fact_ids"]:
            raise ValueError(f"criterion_assessment[{index}] must cite a case fact")
        if item["required"]:
            required_assessments.append(item)
    if status == "criteria_met" and any(
        item["status"] != "met" for item in required_assessments
    ):
        raise ValueError("criteria_met requires every required criterion to be met")
    changed_major_category = not vocab.disease_matches_case_major_category(
        refined, case_major_category
    )
    if status != "criteria_met" and changed_major_category:
        raise ValueError(
            "non-met or indeterminate adjudication must remain within the original case_major_category"
        )
    if changed_major_category:
        if not driven_by:
            raise ValueError("a changed major category requires at least one driving card")
        if not required_assessments:
            raise ValueError("a changed major category requires at least one required criterion")
        if any(item["status"] != "met" for item in required_assessments):
            raise ValueError("a changed major category requires every required criterion to be met")
    _validate_user_review(
        adjudication,
        genes,
        allowed_refined_diseases,
        retrieved_card_ids,
        require_completed_review=require_completed_review,
    )
    return adjudication

def _adjudication_diagnosis_card_ids(adjudication):
    """Return diagnosis cards actually cited/used by Step 3, preserving no extras."""
    selected = set(adjudication.get("driven_by") or [])
    for assessment in adjudication.get("criterion_assessment") or []:
        selected.update(assessment.get("card_ids") or [])
    review = adjudication.get("user_review")
    if isinstance(review, dict) and review.get("decision") in {"agree", "disagree"}:
        selected.update(review.get("card_ids") or [])
    return selected


def step4(
    cards, genes, refined_disease, diagnosis_cards, *, adjudication=None,
    case_major_category=None
):
    normalised_genes = _normalise_genes(list(genes), field="genes")
    _validate_case_disease(refined_disease, normalised_genes, field="refined_disease")
    if case_major_category is None:
        case_major_category = vocab.preferred_case_major_category(refined_disease)
    if case_major_category is not None:
        _validate_case_major_category(case_major_category, normalised_genes)
    wanted = set(normalised_genes)
    retrieved = []
    suppressed = []
    retrieval_scope = {
        category: vocab.retrieval_related_diseases(refined_disease, category)
        for category in DISEASE_FILTERED
    }
    diagnosis_by_id = {card["card_id"]: card for card in diagnosis_cards}
    if adjudication is None:
        # Backward-compatible direct-call behaviour: Step-2 diagnosis cards remain
        # eligible under the old stricter filter.
        selected_diagnosis_ids = set(diagnosis_by_id)
        carry_used_only = False
        broad_major_fallback = False
    else:
        selected_diagnosis_ids = _adjudication_diagnosis_card_ids(adjudication)
        unknown_ids = selected_diagnosis_ids - set(diagnosis_by_id)
        if unknown_ids:
            raise ValueError(
                "adjudication uses diagnosis card(s) absent from Step 2: "
                + ", ".join(sorted(unknown_ids))
            )
        carry_used_only = True
        review = adjudication.get("user_review")
        effective_label = adjudication.get("diagnostic_label")
        if isinstance(review, dict) and review.get("decision") in {"agree", "disagree"}:
            effective_label = review.get("diagnostic_label")
        diagnosis_remains_broad = (
            case_major_category is not None
            and refined_disease == case_major_category
            and (effective_label is None or effective_label == refined_disease)
        )
        broad_major_fallback = (
            adjudication.get("status") == "indeterminate" or diagnosis_remains_broad
        )

    for card in cards:
        category = card["category"]
        matched = match_genes(card, wanted)
        hit = dict(card)
        hit["matched_genes"] = matched

        if category == "diagnosis":
            if card["card_id"] not in selected_diagnosis_ids:
                continue
            if carry_used_only:
                hit["retrieval_match"] = "adjudication_used"
                retrieved.append(hit)
                continue
            # Legacy direct-call path below keeps the historical Step-4 filtering.

        if category == "germline":
            if matched:
                hit["retrieval_match"] = "gene_only"
                retrieved.append(hit)
            continue
        if category not in DISEASE_FILTERED:
            continue

        diseases = card["diseases"]
        if not diseases:
            if matched:
                suppressed.append(hit)
            continue
        exact_match = refined_disease in diseases
        related = set(retrieval_scope.get(category, []))
        related_matches = [disease for disease in diseases if disease in related]
        major_matches = []
        if broad_major_fallback and case_major_category is not None:
            major_matches = [
                disease for disease in diseases
                if vocab.disease_matches_case_major_category(disease, case_major_category)
            ]
        disease_matched = exact_match or bool(related_matches) or bool(major_matches)
        geneless_allowed = not card["genes"] and category in {"diagnosis", "treatment"}
        if disease_matched and (matched or geneless_allowed):
            if exact_match:
                hit["retrieval_match"] = "exact_geneless" if geneless_allowed else "exact"
            elif related_matches:
                hit["retrieval_match"] = "related_geneless" if geneless_allowed else "related"
                hit["matched_retrieval_related_diseases"] = related_matches
            else:
                hit["retrieval_match"] = "major_category_geneless" if geneless_allowed else "major_category"
                hit["matched_case_major_category"] = case_major_category
            retrieved.append(hit)
            continue
        if matched:
            suppressed.append(hit)

    assessed = {gene for hit in retrieved for gene in hit["matched_genes"]}
    assessed |= {gene for hit in suppressed for gene in hit["matched_genes"]}
    not_assessed = sorted(wanted - assessed)
    by_disease = {}
    for hit in suppressed:
        for disease in hit["diseases"]:
            by_disease[disease] = by_disease.get(disease, 0) + 1
    return {
        "retrieval_scope": {
            "case_disease": refined_disease,
            "case_major_category": case_major_category,
            "broad_major_category_fallback": broad_major_fallback,
            "retrieval_related": retrieval_scope,
        },
        "retrieved": sorted(retrieved, key=lambda item: item["card_id"]),
        "suppressed": {
            "count": len(suppressed),
            "by_disease": dict(sorted(by_disease.items())),
            "cards": sorted(
                (
                    {
                        "card_id": hit["card_id"],
                        "genes": hit["genes"],
                        "diseases": hit["diseases"],
                        "category": hit["category"],
                    }
                    for hit in suppressed
                ),
                key=lambda item: item["card_id"],
            ),
        },
        "not_assessed": [
            {"gene": gene, "reason": "no card in any category in this corpus version"}
            for gene in not_assessed
        ],
    }


def run_diagnosis(args):
    corpus, _index, digest = load_corpus(args.corpus, args.index)
    cards = blacklist_cards(flatten(corpus), args.blacklist)
    case_input = None
    overrides = []
    if args.case_input:
        case_input = validate_case_input(args.case_input)
    if args.genes:
        genes = [gene.upper() for gene in args.genes]
        if case_input:
            overrides.append("genes")
    elif case_input:
        genes = case_input["genes"]
    else:
        raise ValueError("--genes is required unless --case-input is provided")
    if args.provisional_disease is not None:
        provisional = args.provisional_disease
        if case_input:
            overrides.append("provisional-disease")
    elif case_input:
        provisional = case_input["provisional_disease"]
    else:
        provisional = vocab.UNSPECIFIED_DISEASE
    if args.case_major_category is not None:
        case_major_category = args.case_major_category
        if case_input:
            overrides.append("case-major-category")
    elif case_input:
        case_major_category = case_input["case_major_category"]
    else:
        case_major_category = None
    if args.case_facts:
        facts_document = json.loads(args.case_facts.read_text(encoding="utf-8"))
        case_facts = facts_document.get("case_facts") if isinstance(facts_document, dict) else facts_document
        if case_input:
            overrides.append("case-facts")
    elif case_input:
        case_facts = case_input["case_facts"]
    else:
        raise ValueError("--case-facts is required unless --case-input is provided")
    for field in overrides:
        flag = field if field != "provisional-disease" else "provisional-disease"
        print(f"[retrieve] overriding case-input {field} from --{flag}", file=sys.stderr)
    result = step2(
        cards, genes, provisional, case_facts, case_major_category=case_major_category
    )
    result["corpus"] = {"path": str(args.corpus), "index": str(args.index)}
    result["provenance"] = provenance(
        corpus, args.corpus, args.index, digest,
        [card["card_id"] for card in result["diagnosis_cards"]],
    )
    result["step3_instruction"] = (
        "Use prompts/workflow/adjudicate_diagnosis.md to compare only case_facts with "
        "the retrieved diagnosis_cards. provisional_disease is the supplied free-text "
        "starting diagnosis; refined_disease must be one allowed canonical value. A "
        "change outside case_major_category requires fully met diagnostic criteria."
    )
    return result

def run_full(args):
    step2_result = load_step_json(args.diagnosis_result)
    adjudication = json.loads(Path(args.adjudication_result).read_text(encoding="utf-8"))
    validate_adjudication(
        step2_result,
        adjudication,
        require_completed_review=True,
    )
    corpus_path = Path(args.corpus or step2_result["corpus"]["path"])
    index_path = Path(args.index or step2_result["corpus"]["index"])
    corpus, _index, digest = load_corpus(corpus_path, index_path)
    provisional = step2_result["provisional_disease"]
    refined = adjudication["downstream_filter_disease"]
    genes = args.genes if args.genes is not None else step2_result["genes"]
    cards = blacklist_cards(flatten(corpus), args.blacklist)
    eligible_card_ids = {card["card_id"] for card in cards}
    newly_blocked_diagnosis = sorted(
        _adjudication_diagnosis_card_ids(adjudication) - eligible_card_ids
    )
    if newly_blocked_diagnosis:
        raise ValueError(
            "blacklist excludes diagnosis card(s) used by the completed adjudication: "
            + ", ".join(newly_blocked_diagnosis)
            + ". Rerun diagnosis and adjudication under the current blacklist."
        )
    result = step4(
        cards, genes, refined, step2_result["diagnosis_cards"],
        adjudication=adjudication,
        case_major_category=step2_result["case_major_category"],
    )
    result = {
        "step": 4,
        "genes": sorted({gene.upper() for gene in genes}),
        "case_major_category": step2_result["case_major_category"],
        "provisional_disease": provisional,
        "refined_disease": refined,
        "diagnostic_adjudication": adjudication,
        **result,
    }
    result["provenance"] = provenance(
        corpus, corpus_path, index_path, digest,
        [card["card_id"] for card in result["retrieved"]],
    )
    return result

def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    diagnosis = sub.add_parser("diagnosis", help="step 2")
    diagnosis.add_argument("--case-input", type=Path,
                           help="JSON object with case_major_category, provisional_disease, genes, and case_facts")
    diagnosis.add_argument("--genes", nargs="+")
    diagnosis.add_argument("--case-facts", type=Path,
                           help="JSON array, or object with case_facts array")
    diagnosis.add_argument("--provisional-disease", default=None)
    diagnosis.add_argument(
        "--case-major-category", default=None, choices=vocab.CASE_MAJOR_CATEGORIES
    )
    diagnosis.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    diagnosis.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    diagnosis.add_argument("--blacklist", type=Path, default=DEFAULT_BLACKLIST,
                           help="YAML card eligibility policy")
    full = sub.add_parser("full", help="step 4")
    full.add_argument("--diagnosis-result", type=Path, required=True)
    full.add_argument("--adjudication-result", type=Path, required=True,
                      help="JSON emitted under prompts/workflow/adjudicate_diagnosis.md")
    full.add_argument("--genes", nargs="+")
    full.add_argument("--corpus", type=Path)
    full.add_argument("--index", type=Path)
    full.add_argument("--blacklist", type=Path, default=DEFAULT_BLACKLIST,
                      help="YAML card eligibility policy")
    diagnosis.add_argument("--output", type=Path, help="write Step-2 Markdown here instead of stdout")
    full.add_argument("--output", type=Path, help="write Step-4 JSON bundle here instead of stdout")
    args = parser.parse_args()
    try:
        result = run_diagnosis(args) if args.command == "diagnosis" else run_full(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        sys.exit(f"retrieval failed: {exc}")
    payload = (
        render_step_markdown(result)
        if args.command == "diagnosis"
        else json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    )
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8")
        if args.command == "diagnosis":
            write_step_json(result, args.output.with_suffix(".json"))
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        print(payload, end="" if payload.endswith("\n") else "\n")


if __name__ == "__main__":
    main()
