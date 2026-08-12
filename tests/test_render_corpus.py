import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import render_corpus  # noqa: E402


class RenderCorpusTests(unittest.TestCase):
    @staticmethod
    def card(key, interpretation):
        return {
            "card_id": f"{key}-C0001",
            "category": "prognosis",
            "genes": ["TP53"],
            "diseases": ["MDS"],
            "disease_ancestors": [],
            "evidence_tier": "multivariable-adjusted",
            "interpretation": interpretation,
            "locator": "line 10",
            "secondary_citation": None,
        }

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

    def test_acceptance_version_provenance_combines_all_accepted_changes(self):
        provenance = render_corpus.acceptance_version_provenance(
            {
                "accepted_in_version": "0.1.5",
                "version_history": ["0.1.5", "0.1.8"],
                "latest_version": "0.1.8",
                "supplements": [
                    {
                        "accepted_at": "2026-08-10T00:00:00+00:00",
                        "accepted_in_version": "0.1.9",
                    }
                ],
                "revisions": [
                    {
                        "accepted_at": "2026-08-11T00:00:00+00:00",
                        "accepted_in_version": "0.1.9",
                    }
                ],
                "redos": [
                    {
                        "accepted_at": "2026-08-12T00:00:00+00:00",
                        "accepted_in_version": "0.2.0",
                    }
                ],
            }
        )
        self.assertEqual(provenance["accepted_in_version"], "0.1.5")
        self.assertEqual(
            provenance["acceptance_version_history"],
            ["0.1.5", "0.1.8", "0.1.9", "0.2.0"],
        )
        self.assertEqual(provenance["latest_accepted_in_version"], "0.2.0")

    def test_main_renders_accepted_corpus_by_default(self):
        key = "paper-one"
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            index_path = root / "index.json"
            corpus_path = root / "corpus.json"
            index_path.write_text(
                json.dumps(
                    {
                        "papers": {
                            key: {
                                "citation_display": "Accepted citation.",
                                "accepted_in_version": "0.1.7",
                                "card_ids": [f"{key}-C0001"],
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            corpus_path.write_text(
                json.dumps({"cards": [self.card(key, "Accepted interpretation.")]}),
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                render_corpus.main(
                    ["--key", key, "--index", str(index_path), "--corpus", str(corpus_path)]
                )
        self.assertIn("Accepted citation.", output.getvalue())
        self.assertIn("Accepted interpretation.", output.getvalue())
        self.assertIn("**Accepted in:** 0.1.7", output.getvalue())
        self.assertIn("**Version history:** 0.1.7", output.getvalue())
        self.assertIn("**Latest version accepted:** 0.1.7", output.getvalue())

    def test_main_from_work_renders_paper_final_json(self):
        key = "paper-one"
        with tempfile.TemporaryDirectory() as temp:
            work_dir = Path(temp) / "work"
            working = work_dir / key
            working.mkdir(parents=True)
            (working / "metadata.json").write_text(
                json.dumps(
                    {
                        "publication_key": key,
                        "citation": {"display": "Working citation."},
                    }
                ),
                encoding="utf-8",
            )
            (working / "paper.final.json").write_text(
                json.dumps({"cards": [self.card(key, "Working interpretation.")]}),
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                render_corpus.main(
                    ["--key", key, "--from-work", "--work-dir", str(work_dir)]
                )
        self.assertIn("Working citation.", output.getvalue())
        self.assertIn("Working interpretation.", output.getvalue())
        self.assertIn("**Accepted in:** —", output.getvalue())
        self.assertIn("**Version history:** —", output.getvalue())
        self.assertIn("**Latest version accepted:** —", output.getvalue())

    def test_main_from_accept_renders_accepted_final_json(self):
        key = "paper-one"
        with tempfile.TemporaryDirectory() as temp:
            accept_dir = Path(temp) / "accept"
            accept_dir.mkdir()
            (accept_dir / f"{key}.final.json").write_text(
                json.dumps(
                    {
                        "accepted_in_version": "0.1.7",
                        "latest_version": "0.1.8",
                        "version_history": ["0.1.7", "0.1.8"],
                        "redos": [
                            {
                                "redo": 1,
                                "accepted_at": "2026-08-12T04:26:15+00:00",
                                "accepted_in_version": "0.2.0",
                            }
                        ],
                        "metadata": {
                            "publication_key": key,
                            "citation": {"display": "Accepted-package citation."},
                        },
                        "final": {
                            "cards": [self.card(key, "Accepted-package interpretation.")]
                        },
                    }
                ),
                encoding="utf-8",
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                render_corpus.main(
                    ["--key", key, "--from-accept", "--accept-dir", str(accept_dir)]
                )
        self.assertIn("Accepted-package citation.", output.getvalue())
        self.assertIn("Accepted-package interpretation.", output.getvalue())
        self.assertIn("**Accepted in:** 0.1.7", output.getvalue())
        self.assertIn("**Version history:** 0.1.7 → 0.1.8 → 0.2.0", output.getvalue())
        self.assertIn("**Latest version accepted:** 0.2.0", output.getvalue())

    def test_explicit_sources_require_key_mode(self):
        for source in ("--from-work", "--from-accept"):
            with self.subTest(source=source):
                error = io.StringIO()
                with contextlib.redirect_stderr(error), self.assertRaises(SystemExit) as raised:
                    render_corpus.main(["--list", source])
                self.assertEqual(raised.exception.code, 2)
                self.assertIn("require --key", error.getvalue())

    def test_work_and_accept_sources_are_mutually_exclusive(self):
        error = io.StringIO()
        with contextlib.redirect_stderr(error), self.assertRaises(SystemExit) as raised:
            render_corpus.main(
                ["--key", "paper-one", "--from-work", "--from-accept"]
            )
        self.assertEqual(raised.exception.code, 2)
        self.assertIn("not allowed with argument", error.getvalue())


if __name__ == "__main__":
    unittest.main()
