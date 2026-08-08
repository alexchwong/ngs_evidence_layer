#!/usr/bin/env python3
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_module():
    spec = importlib.util.spec_from_file_location(
        "build_secondary_source_backlog",
        ROOT / "scripts" / "build_secondary_source_backlog.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


backlog = load_module()


def write_json(path, document):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")


class SecondarySourceBacklogTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.archive = self.root / "archive"
        self.archive.mkdir()
        self.corpus = self.root / "output" / "corpus" / "nel.corpus.json"
        write_json(
            self.corpus,
            {
                "generated_at": "2026-08-08T00:00:00+00:00",
                "publications": [],
            },
        )

    def tearDown(self):
        self.tmp.cleanup()

    def add_archive(self, key, cards, review_results, final_card_ids=()):
        folder = self.archive / key
        citation = {
            "authors": ["Curator A"],
            "title": f"Curated {key}",
            "journal": "Journal",
            "year": 2024,
            "display": f"Curator A. Curated {key}. Journal. 2024.",
        }
        write_json(folder / "metadata.json", {"publication_key": key, "citation": citation})
        write_json(folder / "paper.provisional-001.json", {"cards": cards})
        write_json(folder / "paper.review-001.json", {"card_results": review_results})
        final_cards = [next(card for card in cards if card["card_id"] == card_id) for card_id in final_card_ids]
        write_json(folder / "paper.final.json", {"cards": final_cards})
        return folder

    @staticmethod
    def secondary_card(card_id, source_title="Original Study", source_year=2018):
        return {
            "card_id": card_id,
            "category": "prognosis",
            "genes": ["TP53"],
            "diseases": ["AML"],
            "interpretation": f"Interpretation from {source_title}.",
            "locator": "Discussion",
            "evidence_tier": "restated secondary",
            "secondary_citation": {
                "authors": ["Source A"],
                "title": source_title,
                "journal": "Source Journal",
                "year": source_year,
                "display": f"Source A. {source_title}. Source Journal. {source_year}.",
            },
        }

    @staticmethod
    def failed(card_id):
        return {
            "card_id": card_id,
            "verdict": "fail",
            "details": {
                "failure_type": "unsupported_assertion",
                "reason": "The current paper only restates the cited source.",
                "defensibility": "Potentially defensible from the original source.",
                "suggested_action": {
                    "category": "delete_card",
                    "detail": "Delete this secondary restatement.",
                },
            },
        }

    def test_tracks_only_failed_removed_cards_with_secondary_citations(self):
        removed = self.secondary_card("removed")
        retained = self.secondary_card("retained")
        passed = self.secondary_card("passed")
        primary = dict(self.secondary_card("primary"), secondary_citation=None)
        self.add_archive(
            "paper-one",
            [removed, retained, passed, primary],
            [
                self.failed("removed"),
                self.failed("retained"),
                {"card_id": "passed", "verdict": "pass"},
                self.failed("primary"),
            ],
            final_card_ids=("retained", "passed"),
        )

        result = backlog.build_backlog(self.archive, self.corpus)
        self.assertEqual(result["counts"]["removed_secondary_cards_found"], 1)
        self.assertEqual(result["counts"]["outstanding_removed_cards"], 1)
        item = result["sources"][0]["removed_cards"][0]
        self.assertEqual(item["card"]["card_id"], "removed")
        self.assertEqual(item["review"]["suggested_action"]["category"], "delete_card")

    def test_groups_same_secondary_source_across_archived_papers(self):
        self.add_archive("paper-one", [self.secondary_card("one")], [self.failed("one")])
        self.add_archive("paper-two", [self.secondary_card("two")], [self.failed("two")])

        result = backlog.build_backlog(self.archive, self.corpus)
        self.assertEqual(result["counts"]["outstanding_source_papers"], 1)
        self.assertEqual(result["sources"][0]["card_count"], 2)
        self.assertEqual(result["sources"][0]["referenced_by_publications"], 2)

    def test_excludes_secondary_source_already_in_corpus_by_normalized_title_and_year(self):
        self.add_archive("paper-one", [self.secondary_card("one")], [self.failed("one")])
        write_json(
            self.corpus,
            {
                "publications": [
                    {
                        "document": {
                            "citation": {
                                "title": "Original Study!",
                                "year": 2018,
                                "doi": "10.1000/example",
                            }
                        }
                    }
                ]
            },
        )

        result = backlog.build_backlog(self.archive, self.corpus)
        self.assertEqual(result["sources"], [])
        self.assertEqual(result["counts"]["removed_cards_excluded_already_in_corpus"], 1)
        self.assertEqual(result["counts"]["source_papers_already_in_corpus"], 1)

    def test_markdown_contains_interpretation_and_review_reason(self):
        self.add_archive("paper-one", [self.secondary_card("one")], [self.failed("one")])
        rendered = backlog.render_markdown(backlog.build_backlog(self.archive, self.corpus))
        self.assertIn("Original Study", rendered)
        self.assertIn("Interpretation from Original Study.", rendered)
        self.assertIn("only restates the cited source", rendered)


if __name__ == "__main__":
    unittest.main()
