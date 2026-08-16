#!/usr/bin/env python3
"""Build a single self-contained HTML browser for the accepted card corpus.

Reads the corpus JSON, embeds one record per card (id, interpretation, paper,
diseases, genes, category, tier) and writes a static page that filters cards by
paper, disease, gene and category. Rendered output is one interpretation per
card, prepended by its card ID.

Usage:
  build_card_browser.py [--corpus output/corpus/nel.corpus.json]
                        [--output output/reports/card-browser.html]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CORPUS = REPO_ROOT / "output" / "corpus" / "nel.corpus.json"
DEFAULT_OUTPUT = REPO_ROOT / "output" / "reports" / "card-browser.html"
TEMPLATE = Path(__file__).resolve().parent / "assets" / "card_browser_template.html"


def collect(corpus_path: Path) -> dict:
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    papers = []
    cards = []
    for entry in corpus.get("publications", []):
        document = entry["document"]
        key = document["publication_key"]
        citation = document.get("citation", {})
        papers.append(
            {
                "key": key,
                "nickname": document.get("paper_nickname") or key,
                "display": citation.get("display", ""),
                "journal": citation.get("journal", ""),
                "year": citation.get("year"),
                "type": document.get("publication_type", ""),
            }
        )
        for card in document.get("cards", []):
            cards.append(
                {
                    "id": card["card_id"],
                    "paper": key,
                    "category": card.get("category", ""),
                    "tier": card.get("evidence_tier", ""),
                    "genes": card.get("genes", []),
                    "diseases": card.get("diseases", []),
                    "text": card.get("interpretation", ""),
                }
            )
    papers.sort(key=lambda item: (-(item["year"] or 0), item["nickname"]))
    cards.sort(key=lambda item: item["id"])
    return {
        "corpusVersion": corpus.get("corpus_version"),
        "generatedAt": corpus.get("generated_at"),
        "papers": papers,
        "cards": cards,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    data = collect(args.corpus)
    template = TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")
    html = template.replace("/*__CARD_DATA__*/null", payload)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(html, encoding="utf-8")
    print(f"{args.output} ({len(data['cards'])} cards, {len(data['papers'])} papers)")


if __name__ == "__main__":
    main()
