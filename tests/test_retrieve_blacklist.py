import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.core import corpus as retrieve  # noqa: E402


def cards():
    return [
        {
            "card_id": "paper-a-C0001",
            "publication_key": "paper-a",
            "category": "diagnosis",
            "genes": ["TP53"],
        },
        {
            "card_id": "paper-a-C0002",
            "publication_key": "paper-a",
            "category": "treatment",
            "genes": ["NPM1"],
        },
        {
            "card_id": "paper-a-C0003",
            "publication_key": "paper-a",
            "category": "diagnosis",
            "genes": [],
        },
        {
            "card_id": "paper-b-C0001",
            "publication_key": "paper-b",
            "category": "prognosis",
            "genes": ["TP53", "DNMT3A"],
        },
    ]


def write_policy(tmp_path, document):
    path = tmp_path / "blacklist.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def apply(tmp_path, document):
    source = cards()
    config = retrieve.load_blacklist(write_policy(tmp_path, document), source)
    allowed, excluded = retrieve.apply_blacklist(source, config)
    return [c["card_id"] for c in allowed], [c["card_id"] for c in excluded]


class RetrieveBlacklistTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.tmp_path = Path(self.temp_dir.name)

    def test_empty_policy_changes_nothing(self):
        allowed, excluded = apply(self.tmp_path, {"enabled": True})
        self.assertEqual(allowed, [c["card_id"] for c in cards()])
        self.assertEqual(excluded, [])

    def test_paper_can_be_disabled(self):
        allowed, excluded = apply(
            self.tmp_path, {"papers": {"paper-a": {"enabled": False}}}
        )
        self.assertEqual(allowed, ["paper-b-C0001"])
        self.assertEqual(
            excluded, ["paper-a-C0001", "paper-a-C0002", "paper-a-C0003"]
        )

    def test_category_include_restricts_one_paper(self):
        allowed, _ = apply(
            self.tmp_path,
            {"papers": {"paper-a": {"categories": {"include": ["diagnosis"]}}}},
        )
        self.assertEqual(
            allowed, ["paper-a-C0001", "paper-a-C0003", "paper-b-C0001"]
        )

    def test_gene_include_excludes_geneless_cards(self):
        allowed, _ = apply(
            self.tmp_path,
            {"papers": {"paper-a": {"genes": {"include": ["tp53"]}}}},
        )
        self.assertEqual(allowed, ["paper-a-C0001", "paper-b-C0001"])

    def test_gene_exclude_rejects_card_with_any_matching_gene(self):
        allowed, _ = apply(
            self.tmp_path,
            {"global": {"genes": {"exclude": ["DNMT3A"]}}},
        )
        self.assertEqual(
            allowed, ["paper-a-C0001", "paper-a-C0002", "paper-a-C0003"]
        )

    def test_card_include_is_supported(self):
        allowed, _ = apply(
            self.tmp_path,
            {"papers": {"paper-a": {"cards": {"include": ["paper-a-C0001"]}}}},
        )
        self.assertEqual(allowed, ["paper-a-C0001", "paper-b-C0001"])

    def test_card_exclude_is_supported(self):
        allowed, _ = apply(
            self.tmp_path,
            {"papers": {"paper-a": {"cards": {"exclude": ["paper-a-C0002"]}}}},
        )
        self.assertEqual(
            allowed, ["paper-a-C0001", "paper-a-C0003", "paper-b-C0001"]
        )

    def test_global_and_paper_rules_are_anded(self):
        allowed, _ = apply(
            self.tmp_path,
            {
                "global": {"categories": {"include": ["diagnosis", "prognosis"]}},
                "papers": {"paper-a": {"genes": {"include": ["TP53"]}}},
            },
        )
        self.assertEqual(allowed, ["paper-a-C0001", "paper-b-C0001"])

    def test_unknown_publication_fails_loudly(self):
        with self.assertRaisesRegex(ValueError, "unknown publication_key"):
            retrieve.load_blacklist(
                write_policy(
                    self.tmp_path,
                    {"papers": {"not-a-paper": {"enabled": False}}},
                ),
                cards(),
            )

    def test_unknown_or_wrong_paper_card_fails_loudly(self):
        with self.assertRaisesRegex(ValueError, "not in that paper"):
            retrieve.load_blacklist(
                write_policy(
                    self.tmp_path,
                    {
                        "papers": {
                            "paper-a": {
                                "cards": {"exclude": ["paper-b-C0001"]}
                            }
                        }
                    },
                ),
                cards(),
            )

    def test_include_exclude_overlap_fails_loudly(self):
        with self.assertRaisesRegex(ValueError, "includes and excludes the same"):
            retrieve.load_blacklist(
                write_policy(
                    self.tmp_path,
                    {
                        "papers": {
                            "paper-a": {
                                "categories": {
                                    "include": ["diagnosis"],
                                    "exclude": ["diagnosis"],
                                }
                            }
                        }
                    },
                ),
                cards(),
            )

    def test_invalid_json_fails_loudly(self):
        path = self.tmp_path / "blacklist.json"
        path.write_text("enabled: true\n", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "blacklist JSON is invalid"):
            retrieve.load_blacklist(path, cards())


if __name__ == "__main__":
    unittest.main()
