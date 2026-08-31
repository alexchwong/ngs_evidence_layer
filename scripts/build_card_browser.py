#!/usr/bin/env python3
"""Build a single self-contained HTML browser for the incorporated card corpus.

The default browser is corpus-only and reads exclusively from
``output/corpus/nel.corpus.json`` (or ``--corpus``). ``--full`` renders the same
browser with accepted evidence and provenance attached to each card. Full mode
requires matching ``accept/<publication_key>.final.json`` packages but never
reads or requires ``archive/``.

Usage:
  build_card_browser.py [--corpus output/corpus/nel.corpus.json]
                        [--output output/reports/card-browser.html]
  build_card_browser.py --full [--accept-dir accept]
                        [--output evidence/card-browser-full.html]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CORPUS = REPO_ROOT / "output" / "corpus" / "nel.corpus.json"
DEFAULT_OUTPUT = REPO_ROOT / "output" / "reports" / "card-browser.html"
DEFAULT_FULL_OUTPUT = REPO_ROOT / "evidence" / "card-browser-full.html"
DEFAULT_ACCEPT_DIR = REPO_ROOT / "accept"
TEMPLATE = Path(__file__).resolve().parent / "assets" / "card_browser_template.html"


def _load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object: {path}")
    return value


def _accepted_package(publication_key: str, accept_dir: Path) -> dict:
    path = accept_dir / f"{publication_key}.final.json"
    return _load_json(path, "accepted package")


def _full_details(entry: dict, accept_dir: Path) -> tuple[dict, dict[str, dict]]:
    """Return paper-level detail and evidence indexed by card ID.

    Full mode verifies that the accepted package still matches the incorporated
    corpus. It intentionally uses ``accept/`` only; archive history is neither
    read nor required.
    """
    document = entry["document"]
    source = entry.get("source", {})
    publication_key = document["publication_key"]
    envelope = _accepted_package(publication_key, accept_dir)
    package = envelope.get("final")
    if not isinstance(package, dict):
        raise ValueError(
            f"accepted package has no object-valued final package: "
            f"{accept_dir / (publication_key + '.final.json')}"
        )

    package_cards = package.get("cards")
    evidence_items = package.get("evidence")
    if not isinstance(package_cards, list) or not isinstance(evidence_items, list):
        raise ValueError(
            f"accepted package final.cards/final.evidence must be arrays: {publication_key}"
        )

    accepted_cards: dict[str, dict] = {}
    for card in package_cards:
        if not isinstance(card, dict) or not card.get("card_id"):
            raise ValueError(f"accepted package contains an invalid card: {publication_key}")
        card_id = card["card_id"]
        if card_id in accepted_cards:
            raise ValueError(f"accepted package contains duplicate card_id {card_id}")
        accepted_cards[card_id] = card

    evidence_by_card: dict[str, dict] = {}
    for evidence in evidence_items:
        if not isinstance(evidence, dict) or not evidence.get("card_id"):
            raise ValueError(f"accepted package contains invalid evidence: {publication_key}")
        card_id = evidence["card_id"]
        if card_id in evidence_by_card:
            raise ValueError(f"accepted package contains duplicate evidence for {card_id}")
        evidence_by_card[card_id] = evidence

    corpus_cards = {card["card_id"]: card for card in document.get("cards", [])}
    corpus_ids = set(corpus_cards)
    accepted_ids = set(accepted_cards)
    evidence_ids = set(evidence_by_card)
    if accepted_ids != corpus_ids or evidence_ids != corpus_ids:
        missing_cards = sorted(corpus_ids - accepted_ids)
        extra_cards = sorted(accepted_ids - corpus_ids)
        missing_evidence = sorted(corpus_ids - evidence_ids)
        extra_evidence = sorted(evidence_ids - corpus_ids)
        parts = []
        if missing_cards:
            parts.append("missing accepted cards: " + ", ".join(missing_cards))
        if extra_cards:
            parts.append("extra accepted cards: " + ", ".join(extra_cards))
        if missing_evidence:
            parts.append("missing evidence: " + ", ".join(missing_evidence))
        if extra_evidence:
            parts.append("extra evidence: " + ", ".join(extra_evidence))
        raise ValueError(
            f"accepted package does not match incorporated corpus for {publication_key}; "
            + "; ".join(parts)
            + ". Re-run incorporation before building --full."
        )

    for card_id, corpus_card in corpus_cards.items():
        comparable_corpus = {k: v for k, v in corpus_card.items() if k != "disease_ancestors"}
        comparable_accepted = {
            k: v for k, v in accepted_cards[card_id].items() if k != "disease_ancestors"
        }
        if comparable_accepted != comparable_corpus:
            raise ValueError(
                f"accepted card {card_id} differs from the incorporated corpus. "
                "Re-run incorporation before building --full."
            )

    acceptance = {key: value for key, value in envelope.items() if key != "final"}
    if not acceptance.get("latest_version"):
        modifications = []
        for field in ("supplements", "revisions", "redos"):
            entries = envelope.get(field) or []
            for item in entries:
                accepted_time = item.get("accepted_at")
                version = item.get("accepted_in_version")
                if accepted_time and version:
                    modifications.append((accepted_time, version))
        if modifications:
            modifications.sort()
            acceptance["latest_version"] = modifications[-1][1]

    package_fields = {
        key: value for key, value in package.items() if key not in {"cards", "evidence"}
    }
    paper_details = {
        "document": {key: value for key, value in document.items() if key != "cards"},
        "source": source,
        "accepted_package": acceptance,
        "final_package": package_fields,
    }
    return paper_details, evidence_by_card


def collect(
    corpus_path: Path,
    *,
    full: bool = False,
    accept_dir: Path = DEFAULT_ACCEPT_DIR,
) -> dict:
    """Collect browser data.

    Normal mode depends only on the incorporated corpus. Full mode additionally
    requires one matching accepted package for every incorporated publication.
    """
    corpus = _load_json(corpus_path, "corpus")
    papers = []
    cards = []
    missing_packages = []

    for entry in corpus.get("publications", []):
        document = entry["document"]
        key = document["publication_key"]
        citation = document.get("citation", {})
        paper = {
            "key": key,
            "nickname": document.get("paper_nickname") or key,
            "display": citation.get("display", ""),
            "journal": citation.get("journal", ""),
            "year": citation.get("year"),
            "type": document.get("publication_type", ""),
        }

        paper_details = None
        evidence_by_card = {}
        if full:
            package_path = accept_dir / f"{key}.final.json"
            if not package_path.exists():
                missing_packages.append(key)
            else:
                paper_details, evidence_by_card = _full_details(entry, accept_dir)
                paper["details"] = paper_details

        papers.append(paper)
        for card in document.get("cards", []):
            row = {
                "id": card["card_id"],
                "paper": key,
                "category": card.get("category", ""),
                "tier": card.get("evidence_tier", ""),
                "genes": card.get("genes", []),
                "diseases": card.get("diseases", []),
                "text": card.get("interpretation", ""),
            }
            if full and paper_details is not None:
                row["details"] = {
                    "card": card,
                    "evidence": evidence_by_card[card["card_id"]],
                }
            cards.append(row)

    if missing_packages:
        preview = "\n".join(f"  - {key}" for key in missing_packages[:20])
        remainder = len(missing_packages) - 20
        if remainder > 0:
            preview += f"\n  - ... and {remainder} more"
        raise ValueError(
            "FULL CARD BROWSER FAILED:\n"
            f"accepted evidence unavailable for {len(missing_packages)} publication(s):\n"
            f"{preview}\n"
            f"Expected *.final.json packages in: {accept_dir}"
        )

    papers.sort(key=lambda item: (-(item["year"] or 0), item["nickname"]))
    cards.sort(key=lambda item: item["id"])
    return {
        "corpusVersion": corpus.get("corpus_version"),
        "generatedAt": corpus.get("generated_at"),
        "full": full,
        "papers": papers,
        "cards": cards,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="output HTML path (default changes to evidence/card-browser-full.html with --full)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="include accepted evidence and enable the full-detail preview pane",
    )
    parser.add_argument(
        "--accept-dir",
        type=Path,
        default=DEFAULT_ACCEPT_DIR,
        help="accepted package directory used by --full (default: accept)",
    )
    args = parser.parse_args()
    output = args.output or (DEFAULT_FULL_OUTPUT if args.full else DEFAULT_OUTPUT)

    try:
        data = collect(args.corpus, full=args.full, accept_dir=args.accept_dir)
    except ValueError as exc:
        parser.error(str(exc))

    template = TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")
    html = template.replace("/*__CARD_DATA__*/null", payload)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    mode = "full, " if args.full else ""
    print(f"{output} ({mode}{len(data['cards'])} cards, {len(data['papers'])} papers)")


if __name__ == "__main__":
    main()
