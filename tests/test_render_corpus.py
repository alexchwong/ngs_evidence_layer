import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import render_corpus  # noqa: E402


class RenderCorpusTests(unittest.TestCase):
    def test_render_publication_uses_short_card_numbers(self):
        key = "paper-one"
        card_id = f"{key}-C0003"
        index = {
            "papers": {
                key: {
                    "citation_display": "Example citation.",
                    "accepted_in_version": "0.1.7",
                    "card_ids": [card_id],
                }
            }
        }
        corpus = {
            "nested": [
                {
                    "document": {
                        "cards": [
                            {
                                "card_id": card_id,
                                "category": "prognosis",
                                "genes": ["TP53"],
                                "diseases": ["MDS"],
                                "disease_ancestors": [],
                                "evidence_tier": "multivariable-adjusted",
                                "interpretation": "Important interpretation.",
                                "locator": "line 10",
                                "secondary_citation": None,
                            }
                        ]
                    }
                }
            ]
        }
        rendered = render_corpus.render_publication(key, index, corpus)
        self.assertIn("## 0003", rendered)
        self.assertIn(f"`{card_id}`", rendered)
        self.assertIn("Important interpretation.", rendered)

    def test_render_index_contains_keys_and_citations(self):
        rendered = render_corpus.render_index(
            {"papers": {"paper-one": {"citation_display": "Citation.", "card_ids": []}}}
        )
        self.assertIn("`paper-one`", rendered)
        self.assertIn("Citation.", rendered)


if __name__ == "__main__":
    unittest.main()
