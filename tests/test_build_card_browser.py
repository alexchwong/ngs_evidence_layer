#!/usr/bin/env python3
"""Tests for the desktop corpus card browser, including private full mode."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "build_card_browser.py"
spec = importlib.util.spec_from_file_location("build_card_browser", SCRIPT)
browser = importlib.util.module_from_spec(spec)
spec.loader.exec_module(browser)


class BuildCardBrowserTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.accept = self.root / "accept"
        self.accept.mkdir()
        self.corpus_path = self.root / "nel.corpus.json"
        self.key = "fixture-2026-full-browser"
        self.card = {
            "card_id": f"{self.key}-C0001",
            "category": "diagnosis",
            "disease_ancestors": ["myeloid neoplasm"],
            "diseases": ["AML"],
            "evidence_tier": "guideline/classification",
            "genes": ["NPM1"],
            "interpretation": "According to Fixture Classification, NPM1 defines the fixture AML entity.",
            "locator": "Classification table 1",
            "secondary_citation": None,
        }
        self.evidence = {
            "card_id": self.card["card_id"],
            "evidence_type": "table_relation",
            "fragments": [
                {
                    "fragment_id": "F01",
                    "role": "row_header",
                    "quote": "AML with NPM1 mutation",
                    "locator": "Table 1, row 4",
                },
                {
                    "fragment_id": "F02",
                    "role": "cell",
                    "quote": "Defining genetic abnormality",
                    "locator": "Table 1, row 4, column 2",
                },
            ],
            "support_map": {"gene": ["F01"], "disease": ["F01"], "role": ["F02"]},
            "table_relations": [
                {
                    "value_fragment_id": "F02",
                    "header_fragment_ids": ["F01"],
                    "qualifier_fragment_ids": [],
                }
            ],
        }
        self.document = {
            "publication_key": self.key,
            "paper_nickname": "Fixture Classification 2026",
            "citation": {
                "display": "Fixture A, et al. Fixture classification. 2026.",
                "journal": "Fixture Journal",
                "year": 2026,
                "authors": ["Fixture A"],
                "title": "Fixture classification",
                "volume": "1",
                "issue": "1",
                "pages": "1-10",
                "doi": "10.0000/fixture",
                "citation_incomplete": [],
            },
            "publication_type": "guideline",
            "extraction_date": "2026-08-21",
            "extraction_model": "fixture-model",
            "genes_covered": ["NPM1"],
            "diseases_covered": ["AML"],
            "census_entries": 1,
            "cards": [self.card],
        }
        self.source = {
            "input_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "source_filename": "fixture.pdf",
            "source_sha256": "a" * 64,
            "markdown_sha256": "b" * 64,
            "acceptance_path": "confirmed",
            "audit": {"audit_model": "fixture-reviewer"},
            "extraction": {"cards": 1},
            "warnings": [],
        }
        self.corpus = {
            "corpus_version": "1.2",
            "generated_at": "2026-08-21T05:00:00+00:00",
            "publications": [{"source": self.source, "document": self.document}],
        }
        self.corpus_path.write_text(json.dumps(self.corpus), encoding="utf-8")

        accepted_card = {k: v for k, v in self.card.items() if k != "disease_ancestors"}
        self.envelope = {
            "schema_version": "1.5",
            "acceptance_path": "confirmed",
            "accepted_at": "2026-08-21T04:30:00+00:00",
            "accepted_at_source": "confirm",
            "accepted_in_version": "0.2.4-devel",
            "version_history": ["0.2.4-devel"],
            "metadata": {
                "publication_key": self.key,
                "paper_id": self.source["input_id"],
                "source_filename": "fixture.pdf",
                "operator_note": "retained in full raw provenance",
            },
            "final": {
                "extraction_date": "2026-08-21",
                "extraction_model": "fixture-model",
                "paper_nickname": "Fixture Classification 2026",
                "publication_type": "guideline",
                "publication_type_basis": "Fixture authority statement.",
                "genes_covered": ["NPM1"],
                "diseases_covered": ["AML"],
                "census_entries": 1,
                "cards": [accepted_card],
                "evidence": [self.evidence],
                "audit": {"audit_model": "fixture-reviewer"},
            },
        }
        (self.accept / f"{self.key}.final.json").write_text(
            json.dumps(self.envelope), encoding="utf-8"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_compact_mode_remains_corpus_only(self):
        data = browser.collect(self.corpus_path)

        self.assertFalse(data["full"])
        self.assertNotIn("details", data["papers"][0])
        self.assertNotIn("details", data["cards"][0])
        self.assertEqual(data["cards"][0]["text"], self.card["interpretation"])

    def test_full_mode_retains_card_evidence_and_paper_provenance(self):
        data = browser.collect(self.corpus_path, full=True, accept_dir=self.accept)

        self.assertTrue(data["full"])
        row = data["cards"][0]
        paper = data["papers"][0]
        self.assertEqual(row["details"]["card"], self.card)
        self.assertEqual(row["details"]["evidence"], self.evidence)
        self.assertEqual(paper["details"]["source"], self.source)
        self.assertEqual(
            paper["details"]["accepted_package"]["metadata"]["operator_note"],
            "retained in full raw provenance",
        )
        self.assertEqual(
            paper["details"]["final_package"]["publication_type_basis"],
            "Fixture authority statement.",
        )

    def test_full_mode_requires_every_accepted_package(self):
        (self.accept / f"{self.key}.final.json").unlink()

        with self.assertRaisesRegex(ValueError, "accepted evidence unavailable"):
            browser.collect(self.corpus_path, full=True, accept_dir=self.accept)

    def test_full_mode_rejects_stale_accepted_card(self):
        package_path = self.accept / f"{self.key}.final.json"
        envelope = json.loads(package_path.read_text(encoding="utf-8"))
        envelope["final"]["cards"][0]["interpretation"] = "changed after incorporation"
        package_path.write_text(json.dumps(envelope), encoding="utf-8")

        with self.assertRaisesRegex(ValueError, "differs from the incorporated corpus"):
            browser.collect(self.corpus_path, full=True, accept_dir=self.accept)

    def test_full_cli_uses_private_default_and_embeds_preview_data(self):
        output = self.root / "evidence" / "card-browser-full.html"
        argv = [
            str(SCRIPT),
            "--full",
            "--corpus",
            str(self.corpus_path),
            "--accept-dir",
            str(self.accept),
        ]
        with mock.patch.object(browser, "DEFAULT_FULL_OUTPUT", output), mock.patch.object(
            sys, "argv", argv
        ):
            browser.main()

        html = output.read_text(encoding="utf-8")
        self.assertIn("function buildDetail(card)", html)
        self.assertIn("full evidence view", html)
        self.assertIn("AML with NPM1 mutation", html)
        self.assertIn("retained in full raw provenance", html)

        # Selected full-mode layout is filters | complete details | interpretations.
        self.assertIn("grid-template-columns:1fr 3fr 1fr", html)
        self.assertIn(".detail{grid-column:2;grid-row:1}", html)
        self.assertIn(".main{grid-column:3;grid-row:1", html)

        # The middle detail column repeats interpretation first, then renders
        # only the requested card classification, evidence, and acceptance fields.
        self.assertIn('detailSection("Interpretation")', html)
        self.assertIn('detailSection("Classification")', html)
        self.assertIn('addMeta(classificationGrid, "Genes", exact.genes || card.genes)', html)
        self.assertIn('addMeta(classificationGrid, "Category", exact.category || card.category)', html)
        self.assertIn('addMeta(classificationGrid, "Disease", exact.diseases || card.diseases)', html)
        self.assertIn('detailSection("Evidence")', html)
        self.assertIn('"Evidence tier", exact.evidence_tier || card.tier', html)
        self.assertIn('exact.secondary_citation && exact.secondary_citation.display', html)
        self.assertIn('for (const fragment of (evidence.fragments || []))', html)
        self.assertIn('fragment.fragment_id, fragment.role, fragment.locator', html)
        self.assertIn('quote.textContent = fragment.quote || ""', html)
        self.assertIn('detailSection("Acceptance")', html)
        self.assertIn('"Accepted in version", acceptance.accepted_in_version', html)
        self.assertIn('"Version history", acceptance.version_history', html)

        # Arrays use textOrDash's comma-joined presentation, not genes[0]/genes[1]
        # style recursive paths; unrelated raw accepted-package parameters stay hidden.
        self.assertIn('if (Array.isArray(value)) return value.length ? value.join(", ") : "—"', html)
        self.assertNotIn("function flattenParameters(value, prefix, rows)", html)
        self.assertNotIn('parameterSection("Evidence parameters"', html)
        self.assertNotIn('parameterSection("Publication parameters"', html)
        self.assertNotIn('parameterSection("Source parameters"', html)
        self.assertNotIn('parameterSection("Final package parameters"', html)


if __name__ == "__main__":
    unittest.main()
