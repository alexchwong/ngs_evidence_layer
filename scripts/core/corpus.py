"""Corpus loading and card-eligibility mechanics shared by all workflows."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CORPUS = REPO_ROOT / "output/corpus/nel.corpus.json"
DEFAULT_INDEX = REPO_ROOT / "output/corpus/nel.index.json"
DEFAULT_BLACKLIST = REPO_ROOT / "output/corpus/blacklist.json"
CARD_CATEGORIES = {"diagnosis", "prognosis", "treatment", "biomarker", "germline"}

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


def _blacklist_string_list(value, *, field, uppercase=False):
    """Validate one include/exclude list and return normalised unique values."""
    if value is None:
        return []
    if not isinstance(value, list):
        raise ValueError(f"blacklist {field} must be a JSON array")
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
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"blacklist JSON is invalid: {exc}") from exc
    if not isinstance(raw, dict):
        raise ValueError("blacklist root must be a JSON object")
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
